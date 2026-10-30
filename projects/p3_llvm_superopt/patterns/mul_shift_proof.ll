; mul_shift_proof.ll — LLVM IR FileCheck test for the optimization:
;   x * 2^k  →  x << k
;
; Transformation is valid for unsigned integer semantics whenever k is a
; non-negative constant with k < bitwidth(x).  With nuw on the multiply,
; the shift can carry nuw as well; with nsw the shift carries nsw.
;
; Alive2 proof:
; ---
; Name: mul-shift-nuw-i32
; Pre: isPowerOf2(C) && C > 0
; %r = mul nuw i32 %x, C
; =>
; %k = log2(C)
; %r = shl nuw i32 %x, %k
; ---
; Case C = 2^k:
;   mul nuw %x, 2^k  =  %x * 2^k  (no unsigned overflow by pre-condition)
;   shl nuw %x, k    =  %x * 2^k  (shift by k, same unsigned value)
;   Poison: nuw on shl fires iff the shifted-out bits are non-zero, which is
;   exactly the same condition as unsigned overflow of %x * 2^k — so nuw is
;   preserved correctly.  VALID.
;
; Name: mul-shift-nsw-i32
; Pre: isPowerOf2(C) && C > 0
; %r = mul nsw i32 %x, C
; =>
; %k = log2(C)
; %r = shl nsw i32 %x, %k
; ---
; Signed overflow of %x * 2^k  ⟺  shl nsw %x, k fires.
; Both nsw flags guard the same condition.  VALID.
;
; RUN: opt -passes=instcombine -S < %s | FileCheck %s

; ============================================================
; Test 1 — mul nuw by 4 (2^2) → shl nuw 2
; ============================================================
define i32 @test_mul_nuw_4(i32 %x) {
; CHECK-LABEL: @test_mul_nuw_4(
; CHECK:         [[R:%.*]] = shl nuw i32 %x, 2
; CHECK-NEXT:    ret i32 [[R]]
  %r = mul nuw i32 %x, 4
  ret i32 %r
}

; ============================================================
; Test 2 — mul nuw by 8 (2^3) → shl nuw 3
; ============================================================
define i32 @test_mul_nuw_8(i32 %x) {
; CHECK-LABEL: @test_mul_nuw_8(
; CHECK:         [[R:%.*]] = shl nuw i32 %x, 3
; CHECK-NEXT:    ret i32 [[R]]
  %r = mul nuw i32 %x, 8
  ret i32 %r
}

; ============================================================
; Test 3 — mul nsw by 2 (2^1) → shl nsw 1
; ============================================================
define i32 @test_mul_nsw_2(i32 %x) {
; CHECK-LABEL: @test_mul_nsw_2(
; CHECK:         [[R:%.*]] = shl nsw i32 %x, 1
; CHECK-NEXT:    ret i32 [[R]]
  %r = mul nsw i32 %x, 2
  ret i32 %r
}

; ============================================================
; Test 4 — mul nuw by 1024 (2^10), i64 operands
; ============================================================
define i64 @test_mul_nuw_1024_i64(i64 %x) {
; CHECK-LABEL: @test_mul_nuw_1024_i64(
; CHECK:         [[R:%.*]] = shl nuw i64 %x, 10
; CHECK-NEXT:    ret i64 [[R]]
  %r = mul nuw i64 %x, 1024
  ret i64 %r
}

; ============================================================
; Test 5 — negative: mul by 6 (non-power-of-two) must NOT shift-fold
; ============================================================
define i32 @test_mul_non_pow2(i32 %x) {
; CHECK-LABEL: @test_mul_non_pow2(
; CHECK:         %r = mul i32 %x, 6
; CHECK-NEXT:    ret i32 %r
  %r = mul i32 %x, 6
  ret i32 %r
}
