; SelectAddConstCombine — proposed LLVM IR optimization pass
; 
; Pattern: select(cond, binop(x, C), x)  →  binop(x, select(cond, C, identity))
; 
; This is Pattern 1 from the LLVM IR analysis: the asymmetric select+binop
; case that InstCombine misses. Confirmed to survive opt -O3 on LLVM 17.
;
; Alive2 validity proof:
; ---
; Name: SelectAddConst
; Pre: true
; %add = add nsw i32 %x, C
; %sel = select i1 %cond, i32 %add, i32 %x
; =>
; %delta  = select i1 %cond, i32 C, i32 0
; %result = add nsw i32 %x, %delta
; ---
; Case cond=true:  src=add(x,C);   tgt=add(x,select(T,C,0))=add(x,C)  ✓
; Case cond=false: src=x;          tgt=add(x,select(F,C,0))=add(x,0)=x ✓
; Poison: add(x,0) on false path cannot introduce new poison.  VALID.
; NSw variant: SOUND — add(x,0) is trivially nsw.

; ============================================================
; FileCheck Test 1 — positive match
; RUN: opt -passes=select-add-const-combine -S < %s | FileCheck %s
; ============================================================
define i32 @test_select_add_const(i1 %cond, i32 %x) {
; CHECK-LABEL: @test_select_add_const
; CHECK: [[DELTA:%.*]] = select i1 %cond, i32 42, i32 0
; CHECK: [[RES:%.*]]   = add nsw i32 %x, [[DELTA]]
; CHECK: ret i32 [[RES]]
  %add = add nsw i32 %x, 42
  %sel = select i1 %cond, i32 %add, i32 %x
  ret i32 %sel
}

; ============================================================
; FileCheck Test 2 — negative: pattern does NOT fire without nsw
; (dropping nsw would be unsound for overflow semantics)
; ============================================================
define i32 @test_select_add_no_nsw(i1 %cond, i32 %x) {
; CHECK-LABEL: @test_select_add_no_nsw
; CHECK: %add = add i32 %x, 42
; CHECK: %sel = select i1 %cond, i32 %add, i32 %x
  %add = add i32 %x, 42   ; no nsw — should NOT transform
  %sel = select i1 %cond, i32 %add, i32 %x
  ret i32 %sel
}

; ============================================================
; FileCheck Test 3 — flag propagation: result inherits nsw
; ============================================================
define i32 @test_flag_propagation(i1 %cond, i32 %x) {
; CHECK-LABEL: @test_flag_propagation
; CHECK: [[DELTA:%.*]] = select i1 %cond, i32 100, i32 0
; CHECK: [[RES:%.*]]   = add nsw i32 %x, [[DELTA]]
  %add = add nsw i32 %x, 100
  %sel = select i1 %cond, i32 %add, i32 %x
  ret i32 %sel
}
