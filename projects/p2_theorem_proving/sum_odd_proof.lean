-- Lean 4 Proof: Sum of first n odd numbers = n²
-- Theorem: ∀ n ≥ 0, ∑_{k=0}^{n-1} (2k+1) = n²

import Mathlib.Data.Nat.Basic
import Mathlib.Algebra.BigOperators.Basic
import Mathlib.Tactic

open Finset BigOperators

-- Primary statement using Finset.sum
theorem sum_odd_eq_sq (n : ℕ) :
    ∑ k ∈ Finset.range n, (2 * k + 1) = n ^ 2 := by
  induction n with
  | zero => simp
  | succ n ih =>
    rw [Finset.sum_range_succ, ih]
    ring

-- Alternative 1: direct induction with omega
theorem sum_odd_eq_sq' (n : ℕ) :
    ∑ k ∈ Finset.range n, (2 * k + 1) = n ^ 2 := by
  induction n with
  | zero => rfl
  | succ n ih =>
    simp [Finset.sum_range_succ, ih]
    omega

-- Alternative 2: decide for small cases
#eval (∑ k ∈ Finset.range 5, (2 * k + 1) : ℕ)  -- should be 25

-- Related Mathlib lemmas used:
-- Finset.sum_range_succ : ∑ x ∈ Finset.range (n+1), f x = ∑ x ∈ Finset.range n, f x + f n
-- Nat.succ_eq_add_one   : Nat.succ n = n + 1

-- Generalization: The same technique proves
-- ∑_{k=0}^{n-1} k = n*(n-1)/2
theorem sum_range_eq (n : ℕ) :
    2 * ∑ k ∈ Finset.range n, k = n * (n - 1) := by
  induction n with
  | zero => simp
  | succ n ih =>
    rw [Finset.sum_range_succ]
    simp [Nat.mul_add]
    omega
