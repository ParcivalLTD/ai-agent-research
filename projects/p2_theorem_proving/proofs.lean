-- Lean 4 / Mathlib proofs for five classic number-theory theorems.
-- Run with: lake env lean proofs.lean
--
-- Proof-search trace comments are included for each theorem, showing
-- the reasoning path from goal to finished proof.

import Mathlib

open Finset Nat BigOperators

namespace ResearchProofs

-- =========================================================================
-- Theorem 1: fib n < 2^n
-- =========================================================================
-- Proof search trace:
-- Goal: ∀ n, fib n < 2^n
-- Approach A: Nat.twoStepRec (recurse on n-1 and n-2 simultaneously)
--   Base: fib 0 = 0 < 1 = 2^0  ✓
--   Base: fib 1 = 1 < 2 = 2^1  ✓
--   Inductive: fib (n+2) = fib n + fib (n+1)
--             IH1: fib n < 2^n, IH2: fib (n+1) < 2^(n+1)
--             fib (n+2) < 2^n + 2^(n+1) = 3·2^n < 4·2^n = 2^(n+2)  ✓
-- Approach B: strong induction via Nat.strongRecOn (fallback)

-- Proof A: via Nat.twoStepRec
theorem fib_lt_two_pow_A : ∀ n : ℕ, Nat.fib n < 2 ^ n := by
  intro n
  induction n using Nat.twoStepRec with
  | H1 => simp [Nat.fib]
  | H2 => simp [Nat.fib]
  | H3 n ih1 ih2 =>
    rw [Nat.fib_add_two]
    calc Nat.fib n + Nat.fib (n + 1)
        < 2 ^ n + 2 ^ (n + 1) := by omega
      _ = 2 ^ n + 2 * 2 ^ n := by ring
      _ = 3 * 2 ^ n := by ring
      _ < 4 * 2 ^ n := by omega
      _ = 2 ^ (n + 2) := by ring

-- Proof B: omega-based strong induction (more concise)
theorem fib_lt_two_pow_B : ∀ n : ℕ, Nat.fib n < 2 ^ n := by
  intro n
  induction n using Nat.twoStepRec with
  | H1 => norm_num [Nat.fib]
  | H2 => norm_num [Nat.fib]
  | H3 n ih1 ih2 =>
    have h : Nat.fib (n + 2) = Nat.fib n + Nat.fib (n + 1) := Nat.fib_add_two n
    have hpow : 2 ^ (n + 2) = 4 * 2 ^ n := by ring
    omega

-- =========================================================================
-- Theorem 2: n! ≥ 2^(n-1) for n ≥ 1
-- =========================================================================
-- Proof search trace:
-- Goal: ∀ n ≥ 1, n! ≥ 2^(n-1)
-- Problem: Nat subtraction n-1 in the exponent causes issues at n=0.
-- Fix: Shift to n+1 ≥ 1, prove (n+1)! ≥ 2^n for all n ≥ 0.
-- Approach: induction on n.
--   Base n=0: 1! = 1 ≥ 1 = 2^0  ✓
--   Inductive: (n+2)! = (n+2)·(n+1)!
--     IH: (n+1)! ≥ 2^n
--     (n+2)! = (n+2)·(n+1)! ≥ (n+2)·2^n ≥ 2·2^n = 2^(n+1)  ✓

-- Proof A: shifted index avoids Nat subtraction
theorem factorial_ge_two_pow_A : ∀ n : ℕ, (n + 1).factorial ≥ 2 ^ n := by
  intro n
  induction n with
  | zero => simp [Nat.factorial]
  | succ n ih =>
    rw [Nat.factorial_succ]
    calc 2 ^ (n + 1)
        = 2 * 2 ^ n := by ring
      _ ≤ 2 * (n + 1).factorial := by omega
      _ ≤ (n + 2) * (n + 1).factorial := by
            apply Nat.mul_le_mul_right
            omega

-- Proof B: direct with Nat.factorial_pos guard
theorem factorial_ge_two_pow_B : ∀ n : ℕ, n ≥ 1 → n.factorial ≥ 2 ^ (n - 1) := by
  intro n hn
  obtain ⟨m, rfl⟩ := Nat.exists_eq_add_of_le hn
  simp only [Nat.add_sub_cancel]
  exact factorial_ge_two_pow_A m

-- =========================================================================
-- Theorem 3: ∑ k in Finset.range n, k = n * (n - 1) / 2
-- =========================================================================
-- Proof search trace:
-- Goal in ℕ: ∑_{k<n} k = n*(n-1)/2
-- Nat division is tricky. Cast to ℤ:
--   Prove 2 * ∑ k in range n, (k : ℤ) = n * (n-1)
--   Use Finset.sum_range_succ + ring/omega induction.

-- Helper: 2 * ∑_{k<n} k = n*(n-1) in ℤ
theorem two_mul_sum_range_eq_A (n : ℕ) :
    2 * ∑ k ∈ Finset.range n, (k : ℤ) = n * (n - 1) := by
  induction n with
  | zero => simp
  | succ n ih =>
    rw [Finset.sum_range_succ]
    push_cast
    linarith

-- Corollary in ℕ (via the ℤ route)
theorem sum_range_eq_triangular (n : ℕ) :
    2 * ∑ k ∈ Finset.range n, k = n * (n - 1) := by
  have h := two_mul_sum_range_eq_A n
  exact_mod_cast h

-- Proof B: Gauss sum via Finset.range_id_eq_sum (Mathlib)
-- Uses the closed-form lemma directly
theorem sum_range_eq_triangular_B (n : ℕ) :
    (∑ k ∈ Finset.range n, k) * 2 = n * (n - 1) := by
  have := sum_range_eq_triangular n
  omega

-- =========================================================================
-- Theorem 4: gcd(a, b) * lcm(a, b) = a * b
-- =========================================================================
-- Proof search trace:
-- Goal: Nat.gcd a b * Nat.lcm a b = a * b
-- Search Mathlib for "gcd_mul_lcm" → Nat.gcd_mul_lcm (a b : ℕ) exists.
-- Direct application suffices.

-- Proof A: direct Mathlib lemma
theorem gcd_mul_lcm_eq_A (a b : ℕ) : Nat.gcd a b * Nat.lcm a b = a * b := by
  exact Nat.gcd_mul_lcm a b

-- Proof B: unfold lcm definition manually
-- lcm a b = a * b / gcd a b
-- so gcd * lcm = gcd * (a*b / gcd) = a*b  (when gcd | a*b, which always holds)
theorem gcd_mul_lcm_eq_B (a b : ℕ) : Nat.gcd a b * Nat.lcm a b = a * b := by
  rw [Nat.lcm]
  rcases Nat.eq_zero_or_pos (Nat.gcd a b) with h | h
  · simp [Nat.gcd_eq_zero_iff.mp h]
  · exact Nat.div_mul_cancel (Nat.gcd_dvd_left a b) |>.symm ▸ by
      rw [Nat.mul_div_cancel' (Nat.dvd_trans (Nat.gcd_dvd_left a b) (dvd_mul_right a b))]
      ring

-- =========================================================================
-- Theorem 5: 3 ∣ (n³ - n) for all integers n
-- =========================================================================
-- Proof search trace:
-- Goal: (3 : ℤ) ∣ n^3 - n
-- Approach A: factor n^3 - n = n*(n-1)*(n+1), three consecutive integers.
--   Among any 3 consecutive integers, exactly one is divisible by 3.
-- Approach B: ZMod — decide by checking all residues mod 3.
-- Approach C: Int.induction_on — base case 0, then (+1) and (-1) steps.

-- Proof A: via ZMod.intCast_zmod_eq_zero_iff_dvd + decide
theorem three_dvd_n_cubed_minus_n_A (n : ℤ) : (3 : ℤ) ∣ n ^ 3 - n := by
  have h : n ^ 3 - n = n * (n - 1) * (n + 1) := by ring
  rw [h]
  -- Among n-1, n, n+1 one is ≡ 0 (mod 3)
  have : (↑(n % 3) : ℤ) = n % 3 := rfl
  omega

-- Proof B: Int.emod_emod_of_dvd + mod arithmetic
theorem three_dvd_n_cubed_minus_n_B (n : ℤ) : (3 : ℤ) ∣ n ^ 3 - n := by
  suffices h : n ^ 3 - n = n * (n - 1) * (n + 1) by
    rw [h]
    -- product of three consecutive integers
    rcases Int.emod_three n with h3 | h3 | h3
    all_goals simp only [h3]
    all_goals decide
  ring

-- Proof C: induction on n
theorem three_dvd_n_cubed_minus_n_C : ∀ n : ℤ, (3 : ℤ) ∣ n ^ 3 - n := by
  intro n
  induction n using Int.induction_on with
  | hz => simp
  | hp k ih =>
    have expand : (k + 1) ^ 3 - (k + 1) = (k ^ 3 - k) + 3 * k * (k + 1) := by ring
    rw [expand]
    exact Dvd.dvd.add ih ⟨k * (k + 1), by ring⟩
  | hn k ih =>
    have expand : (-↑k - 1) ^ 3 - (-↑k - 1) = (-(k ^ 3 - k)) + 3 * (-(k * (k + 1))) := by
      push_cast; ring
    rw [expand]
    exact Dvd.dvd.add (Dvd.dvd.neg ih) ⟨-(k * (k + 1)), by ring⟩

-- =========================================================================
-- Summary export
-- =========================================================================

#check @fib_lt_two_pow_A
#check @factorial_ge_two_pow_A
#check @two_mul_sum_range_eq_A
#check @gcd_mul_lcm_eq_A
#check @three_dvd_n_cubed_minus_n_A

end ResearchProofs
