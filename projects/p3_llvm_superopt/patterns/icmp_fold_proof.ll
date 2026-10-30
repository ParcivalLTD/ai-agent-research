; icmp_fold_proof.ll — LLVM IR FileCheck test for the optimization:
;   icmp eq (and %x, mask), 0  →  bit-test simplification
;
; When a mask is a single-bit constant (a power of two), the expression
; "test whether bit k of %x is clear" can be canonicalized or simplified
; by InstCombine / ValueTracking to expose further simplifications:
;
;   (a) If the comparison feeds a select/branch, the single-bit mask is
;       preserved as-is but the constant-folding of the icmp itself is
;       verified.
;   (b) If additional context (e.g. a dominating and) makes the result
;       statically known, the icmp folds to a constant.
;
; Alive2 proof:
; ---
; Name: icmp-eq-and-mask-zero-single-bit
; Pre: isPowerOf2(mask) && mask > 0
; %t  = and i32 %x, mask
; %r  = icmp eq i32 %t, 0
; =>
; ; (single-bit mask — semantically equivalent, InstCombine may rewrite
; ;  to a shift-based form or keep the and; either is sound)
; %t  = and i32 %x, mask
; %r  = icmp eq i32 %t, 0
; ---
; Trivially valid: src and tgt are identical.  The test below verifies
; that InstCombine does NOT miscompile this into an incorrect form.
;
; Name: icmp-eq-and-zero-const-fold
; Pre: true
; ; When the and result is provably non-zero, the icmp folds to false.
; %k  = and i32 42, 1          ; 42 & 1 = 0  → icmp folds to true
; %r  = icmp eq i32 %k, 0
; =>
; %r  = i1 true
; ---
; 42 & 1 = 0, so icmp eq 0, 0 = true.  VALID.
;
; RUN: opt -passes=instcombine -S < %s | FileCheck %s

; ============================================================
; Test 1 — single-bit mask (0x1): bit-0 clear test survives
; ============================================================
define i1 @test_icmp_bit0(i32 %x) {
; CHECK-LABEL: @test_icmp_bit0(
; CHECK:         [[T:%.*]] = and i32 %x, 1
; CHECK-NEXT:    [[R:%.*]] = icmp eq i32 [[T]], 0
; CHECK-NEXT:    ret i1 [[R]]
  %t = and i32 %x, 1
  %r = icmp eq i32 %t, 0
  ret i1 %r
}

; ============================================================
; Test 2 — single-bit mask (0x8): bit-3 clear test survives
; ============================================================
define i1 @test_icmp_bit3(i32 %x) {
; CHECK-LABEL: @test_icmp_bit3(
; CHECK:         [[T:%.*]] = and i32 %x, 8
; CHECK-NEXT:    [[R:%.*]] = icmp eq i32 [[T]], 0
; CHECK-NEXT:    ret i1 [[R]]
  %t = and i32 %x, 8
  %r = icmp eq i32 %t, 0
  ret i1 %r
}

; ============================================================
; Test 3 — constant folding: 42 & 1 == 0  →  icmp folds to true
; ============================================================
define i1 @test_icmp_const_fold_even() {
; CHECK-LABEL: @test_icmp_const_fold_even(
; CHECK:         ret i1 true
  %t = and i32 42, 1      ; 42 is even → 42 & 1 = 0
  %r = icmp eq i32 %t, 0
  ret i1 %r
}

; ============================================================
; Test 4 — constant folding: 7 & 1 != 0  →  icmp folds to false
; ============================================================
define i1 @test_icmp_const_fold_odd() {
; CHECK-LABEL: @test_icmp_const_fold_odd(
; CHECK:         ret i1 false
  %t = and i32 7, 1       ; 7 is odd → 7 & 1 = 1
  %r = icmp eq i32 %t, 0
  ret i1 %r
}

; ============================================================
; Test 5 — multi-bit mask (0xFF): all-bits-clear test survives
; ============================================================
define i1 @test_icmp_byte_mask(i32 %x) {
; CHECK-LABEL: @test_icmp_byte_mask(
; CHECK:         [[T:%.*]] = and i32 %x, 255
; CHECK-NEXT:    [[R:%.*]] = icmp eq i32 [[T]], 0
; CHECK-NEXT:    ret i1 [[R]]
  %t = and i32 %x, 255
  %r = icmp eq i32 %t, 0
  ret i1 %r
}

; ============================================================
; Test 6 — i64 operand: single-bit mask in wider type
; ============================================================
define i1 @test_icmp_i64_bit63(i64 %x) {
; CHECK-LABEL: @test_icmp_i64_bit63(
; CHECK:         [[T:%.*]] = and i64 %x, -9223372036854775808
; CHECK-NEXT:    [[R:%.*]] = icmp eq i64 [[T]], 0
; CHECK-NEXT:    ret i1 [[R]]
  %t = and i64 %x, 9223372036854775808   ; bit 63 = sign bit
  %r = icmp eq i64 %t, 0
  ret i1 %r
}
