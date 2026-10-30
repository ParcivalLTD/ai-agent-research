import Mathlib

/-!
# Hard Theorems in Lean 4 (via Mathlib)
A collection of 8 famous theorems with proof sketches.
-/

-- ============================================================
-- 1. Infinitude of Primes
-- ============================================================
-- PROOF SKETCH:
--   Assume finitely many primes p₁, p₂, ..., pₙ.
--   Form N = p₁ * p₂ * ... * pₙ + 1.
--   N > 1 so it has a prime factor q.
--   q divides N and also divides p₁ * ... * pₙ, so q divides 1.
--   Contradiction. Hence infinitely many primes exist.
--   Mathlib provides Nat.infinite_setOf_prime via a direct Euclid argument.
theorem infinitude_of_primes : ∀ n : ℕ, ∃ p : ℕ, p > n ∧ Nat.Prime p := by
  exact fun n => Nat.exists_infinite_primes (n + 1) |>.imp fun p ⟨h1, h2⟩ => ⟨Nat.lt_of_succ_le h1, h2⟩

-- ============================================================
-- 2. Fundamental Theorem of Arithmetic
-- ============================================================
-- PROOF SKETCH:
--   Every natural number n > 1 can be written uniquely as a product of primes.
--   Existence: induct on n; if n is prime we're done; otherwise n = a * b with
--     1 < a, b < n, apply induction to both and concatenate the factorizations.
--   Uniqueness: suppose p₁^a₁ · ... = q₁^b₁ · ...  then since each pᵢ is prime
--     it must divide some qⱼ hence pᵢ = qⱼ; cancel and repeat by induction.
--   Mathlib formalises this via `Nat.factors` and `Nat.factorization`.
theorem fundamental_theorem_of_arithmetic (n : ℕ) (hn : 1 < n) :
    ∃ (f : ℕ →₀ ℕ), (∀ p ∈ f.support, Nat.Prime p) ∧
      n = f.prod (· ^ ·) := by
  exact ⟨n.factorization,
         fun p hp => Nat.prime_of_mem_primeFactors (Nat.support_factorization n ▸ hp),
         (Nat.factorization_prod_pow_eq_self (Nat.one_lt_iff_ne_one.mp hn)).symm⟩

-- ============================================================
-- 3. Cantor's Theorem: No surjection A → P(A)
-- ============================================================
-- PROOF SKETCH:
--   Suppose f : A → Set A is surjective.
--   Define the diagonal set D = { a | a ∉ f(a) }.
--   Since f is surjective there exists d with f(d) = D.
--   Case d ∈ D: then d ∉ f(d) = D, contradiction.
--   Case d ∉ D: then d ∈ f(d) = D, contradiction.
--   In both cases we get a contradiction, so f cannot be surjective.
theorem cantor_no_surjection (A : Type*) : ¬ ∃ f : A → Set A, Function.Surjective f := by
  rintro ⟨f, hf⟩
  exact (cantor_surjective f hf).elim

-- ============================================================
-- 4. Fermat's Little Theorem: a^p ≡ a (mod p)
-- ============================================================
-- PROOF SKETCH:
--   When p ∤ a, consider the map x ↦ a*x on (ℤ/pℤ)*.
--   Multiplying all residues {1,...,p-1} by a permutes them (since gcd(a,p)=1).
--   Thus a^(p-1) * (p-1)! ≡ (p-1)! (mod p), cancel (p-1)! to get a^(p-1) ≡ 1.
--   Multiply both sides by a to get a^p ≡ a (mod p).
--   The general case a^p ≡ a follows by checking a ≡ 0 separately.
--   Mathlib provides `ZMod.pow_card` which handles this directly.
theorem fermat_little (p : ℕ) (hp : Nat.Prime p) (a : ZMod p) :
    a ^ p = a := by
  exact ZMod.pow_card a

-- ============================================================
-- 5. Wilson's Theorem: p prime ↔ (p-1)! ≡ -1 (mod p)
-- ============================================================
-- PROOF SKETCH:
--   (→) If p is prime, work in (ℤ/pℤ)*. Pair each x with x⁻¹.
--     Elements that are self-inverse satisfy x² = 1, so x = ±1.
--     All other elements cancel in pairs; what remains is 1 · (-1) = -1.
--   (←) Suppose (p-1)! ≡ -1 (mod p). Then p ∤ (p-1)!, so p has no factor
--     less than p, meaning p is prime (composite p would have a factor < p
--     appearing in (p-1)!, making (p-1)! ≡ 0, not -1).
--   Mathlib provides `ZMod.wilsons_lemma` and `Nat.Prime.wilsons_lemma`.
theorem wilson (p : ℕ) (hp : Nat.Prime p) :
    ((p - 1).factorial : ZMod p) = -1 := by
  exact ZMod.wilsons_lemma p hp

-- ============================================================
-- 6. Bertrand's Postulate: ∀ n ≥ 1, ∃ prime p, n < p ≤ 2n
-- ============================================================
-- PROOF SKETCH:
--   The classical proof due to Chebyshev (1852) analyses the central
--   binomial coefficient C(2n, n) = (2n)! / (n!)².
--   Step 1: C(2n, n) ≥ 4^n / (2n) showing it is large.
--   Step 2: Every prime p in (n, 2n] divides C(2n, n) to the first power.
--   Step 3: Every prime p ≤ n contributes at most (2n)^(1/2) to C(2n, n).
--   Combining the bounds forces at least one prime in (n, 2n].
--   Mathlib provides `Nat.bertrand` directly.
theorem bertrand_postulate (n : ℕ) (hn : 0 < n) :
    ∃ p : ℕ, Nat.Prime p ∧ n < p ∧ p ≤ 2 * n := by
  exact Nat.bertrand n hn

-- ============================================================
-- 7. Cauchy's Theorem for Groups
-- ============================================================
-- PROOF SKETCH:
--   Let G be a finite group and p a prime dividing |G|.
--   Consider the set S of p-tuples (g₁,...,gₚ) with g₁·...·gₚ = 1.
--   |S| = |G|^(p-1) which is divisible by p.
--   The cyclic group ℤ/pℤ acts on S by cyclic rotation.
--   Fixed points of this action are constant tuples (g,...,g) with g^p = 1.
--   By the orbit-stabiliser theorem, fixed points ≡ |S| ≡ 0 (mod p).
--   Since (e,...,e) is one fixed point there must be another, giving g ≠ e, g^p = 1.
--   Mathlib provides `exists_prime_orderOf_dvd_card`.
theorem cauchy_theorem_groups {G : Type*} [Group G] [Fintype G]
    (p : ℕ) (hp : Nat.Prime p) (hdvd : p ∣ Fintype.card G) :
    ∃ g : G, orderOf g = p := by
  exact exists_prime_orderOf_dvd_card p hdvd

-- ============================================================
-- 8. Schur's Theorem on Monochromatic Solutions
-- ============================================================
-- PROOF SKETCH:
--   For any r-colouring of {1,...,N} with N large enough,
--   there exist x, y, z (not necessarily distinct) of the same colour
--   with x + y = z.  Equivalently, the equation x + y = z has a
--   monochromatic solution.
--   Proof: by Ramsey theory. For each r, find N = S(r) via Ramsey number R(3;r).
--   Colour the complete graph K_N by the colour of vertex differences.
--   Ramsey guarantees a monochromatic triangle {a, b, c} with a < b < c.
--   Set x = b - a, y = c - b, z = c - a; then x + y = z, all same colour.
--   Mathlib's `schur` in Combinatorics.Schur (if available) handles this;
--   otherwise we rely on the Ramsey-theoretic framework.
theorem schur_monochromatic (r : ℕ) (hr : 0 < r) :
    ∃ N : ℕ, ∀ (col : Fin N → Fin r),
      ∃ x y z : Fin N,
        col x = col y ∧ col y = col z ∧
        (x : ℕ) + (y : ℕ) = (z : ℕ) := by
  sorry
-- PROOF SKETCH (continued):
--   The full Lean proof of Schur's theorem requires either:
--   (a) Specialising the Hales-Jewett theorem, or
--   (b) A direct Ramsey-based argument formalised in Mathlib's
--       Combinatorics.Ramsey library.
--   Both paths are non-trivial; the sorry above is a placeholder
--   for the complete formalisation.
