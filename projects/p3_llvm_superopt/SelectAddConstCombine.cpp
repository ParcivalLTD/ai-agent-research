//===-- SelectAddConstCombine.cpp - select+binop+const combine pass -------===//
//
// Part of the LLVM Project, under the Apache License v2.0 with LLVM Exceptions.
// See https://llvm.org/LICENSE.txt for license information.
// SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
//
//===----------------------------------------------------------------------===//
//
// SelectBinOpIdentityCombinePass
// ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
// Transforms:
//   %r = select i1 %cond, %binop(%x, C), %x
// into:
//   %id = <identity element for binop>
//   %c  = select i1 %cond, C, %id
//   %r  = binop %x, %c
//
// Supported operations (with identity elements):
//   add  nsw/nuw  identity = 0
//   sub  (x - select(cond,C,0))  identity = 0
//   or                           identity = 0
//   xor                          identity = 0
//
// The transform is profitable because:
//   1. The dependent load/use of %x moves earlier in the schedule.
//   2. The select operands become scalar integer constants — CSE-friendly.
//   3. On targets with conditional-move instructions (cmov, csel) this
//      produces a single cmov instead of a branch.
//
// Safety:
//   - The original binop must have exactly one use (the select result).
//     Hoisting it would duplicate work otherwise.
//   - nsw/nuw flags are preserved via Value::copyIRFlags.
//   - The identity element is always a poison-safe value (zero).
//
//===----------------------------------------------------------------------===//

#include "llvm/Analysis/ValueTracking.h"
#include "llvm/IR/BasicBlock.h"
#include "llvm/IR/Constants.h"
#include "llvm/IR/Function.h"
#include "llvm/IR/IRBuilder.h"
#include "llvm/IR/Instructions.h"
#include "llvm/IR/IntrinsicInst.h"
#include "llvm/IR/PassManager.h"
#include "llvm/IR/PatternMatch.h"
#include "llvm/Passes/PassBuilder.h"
#include "llvm/Passes/PassPlugin.h"
#include "llvm/Support/Debug.h"
#include "llvm/Transforms/Scalar/InstSimplifyPass.h"
#include "llvm/Transforms/Utils/Local.h"

#define DEBUG_TYPE "select-binop-identity"

using namespace llvm;
using namespace llvm::PatternMatch;

STATISTIC(NumSelectBinOpCombined,
          "Number of select(cond, binop(x,C), x) patterns combined");

namespace {

//===----------------------------------------------------------------------===//
// Helper: get identity element for an instruction opcode
//===----------------------------------------------------------------------===//

/// Return the identity value for \p Opcode over type \p Ty, or nullptr if
/// no simple constant identity exists (e.g. mul's identity 1 is excluded
/// here to stay conservative on nsw/nuw).
static Constant *getIdentityConstant(unsigned Opcode, Type *Ty) {
  switch (Opcode) {
  case Instruction::Add:
  case Instruction::Sub:
  case Instruction::Or:
  case Instruction::Xor:
    return ConstantInt::get(Ty, 0);
  default:
    return nullptr;
  }
}

//===----------------------------------------------------------------------===//
// Core pattern match and transform
//===----------------------------------------------------------------------===//

/// Try to rewrite:
///   %binop = op nsw? nuw? %x, C   (single use)
///   %sel   = select cond, %binop, %x
/// into:
///   %c_sel = select cond, C, identity(op)
///   %r     = op nsw? nuw? %x, %c_sel
///
/// Returns the new instruction on success, nullptr otherwise.
static Value *tryTransform(SelectInst *SI, IRBuilder<> &Builder) {
  // Match:  select cond, binop(x, C), x
  Value *Cond = SI->getCondition();
  Value *TrueVal  = SI->getTrueValue();
  Value *FalseVal = SI->getFalseValue();

  // We require FalseVal == x (the "identity" side).
  // The binop(x, C) must be on the TrueVal side.
  BinaryOperator *BinOp = dyn_cast<BinaryOperator>(TrueVal);
  if (!BinOp)
    return nullptr;

  // The binop must have exactly one use (this select). Cloning it would
  // double the work — only safe when this select is the sole consumer.
  if (!BinOp->hasOneUse())
    return nullptr;

  Value *X = nullptr;
  Constant *C = nullptr;

  // Match binop(x, C) where the non-constant operand must equal FalseVal.
  if (match(BinOp, m_BinOp(m_Value(X), m_Constant(C)))) {
    if (X != FalseVal)
      return nullptr;
  } else if (match(BinOp, m_BinOp(m_Constant(C), m_Value(X)))) {
    if (X != FalseVal)
      return nullptr;
    // For non-commutative ops (sub) the constant must be the RHS.
    if (!BinOp->isCommutative())
      return nullptr;
  } else {
    return nullptr;
  }

  unsigned Opcode = BinOp->getOpcode();
  Constant *Identity = getIdentityConstant(Opcode, C->getType());
  if (!Identity)
    return nullptr;

  LLVM_DEBUG(dbgs() << DEBUG_TYPE << ": transforming:\n"
                    << "  " << *BinOp << "\n"
                    << "  " << *SI << "\n");

  // Build:  %c_sel = select cond, C, Identity
  Builder.SetInsertPoint(SI);
  Value *ConstSel =
      Builder.CreateSelect(Cond, C, Identity, SI->getName() + ".csel");

  // Build:  %r = op X, %c_sel  (same opcode, copy flags)
  Value *NewBinOp = Builder.CreateBinOp(
      static_cast<Instruction::BinaryOps>(Opcode), X, ConstSel,
      SI->getName() + ".opt");

  // Preserve nsw / nuw / exact flags from the original instruction.
  if (auto *NewInst = dyn_cast<Instruction>(NewBinOp))
    NewInst->copyIRFlags(BinOp);

  LLVM_DEBUG(dbgs() << DEBUG_TYPE << ": result:\n"
                    << "  " << *ConstSel << "\n"
                    << "  " << *NewBinOp << "\n");

  ++NumSelectBinOpCombined;
  return NewBinOp;
}

//===----------------------------------------------------------------------===//
// Pass implementation
//===----------------------------------------------------------------------===//

struct SelectBinOpIdentityCombinePass
    : public PassInfoMixin<SelectBinOpIdentityCombinePass> {

  PreservedAnalyses run(Function &F, FunctionAnalysisManager &) {
    bool Changed = false;
    IRBuilder<> Builder(F.getContext());

    for (BasicBlock &BB : F) {
      // Collect selects first to avoid iterator invalidation.
      SmallVector<SelectInst *, 8> Selects;
      for (Instruction &I : BB)
        if (auto *SI = dyn_cast<SelectInst>(&I))
          Selects.push_back(SI);

      for (SelectInst *SI : Selects) {
        if (Value *NewVal = tryTransform(SI, Builder)) {
          SI->replaceAllUsesWith(NewVal);
          SI->eraseFromParent();
          Changed = true;
        }
      }
    }

    return Changed ? PreservedAnalyses::none() : PreservedAnalyses::all();
  }

  static bool isRequired() { return false; }
};

} // namespace

//===----------------------------------------------------------------------===//
// Pass registration
//===----------------------------------------------------------------------===//

// Plugin entry point for opt -load-pass-plugin
extern "C" LLVM_ATTRIBUTE_WEAK ::llvm::PassPluginLibraryInfo
llvmGetPassPluginInfo() {
  return {LLVM_PLUGIN_API_VERSION, "SelectBinOpIdentityCombine", LLVM_VERSION_STRING,
          [](PassBuilder &PB) {
            // Register for explicit use:  opt -passes='select-binop-identity'
            PB.registerPipelineParsingCallback(
                [](StringRef Name, FunctionPassManager &FPM,
                   ArrayRef<PassBuilder::PipelineElement>) {
                  if (Name == "select-binop-identity") {
                    FPM.addPass(SelectBinOpIdentityCombinePass());
                    return true;
                  }
                  return false;
                });
            // Also fire at the peephole extension point (O1+)
            PB.registerPeepholeEPCallback(
                [](FunctionPassManager &FPM, OptimizationLevel) {
                  FPM.addPass(SelectBinOpIdentityCombinePass());
                });
          }};
}
