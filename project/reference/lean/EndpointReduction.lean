/-
A small, conditional audit of the mathematical endpoint only.

This file imports official Mathlib modules, not the large submitted project.
EveryCharacter is an EXPLICIT PARAMETER of the main reductions below.  No proof
of EveryCharacter is supplied here; this file must not be described as an
unconditional local verification of the Riemann hypothesis.

The completed-zeta argument is a readable refactoring of
UpperTheory.riemannHypothesis_of_everyCharacter.  The primitive and imprimitive
Dirichlet arguments follow Formalism.VW.critLine and ClaimStrip respectively.
No submitted project code is executed to produce this file.
-/
import Mathlib.NumberTheory.LSeries.DirichletContinuation
import Mathlib.Tactic.Linarith

namespace EndpointReduction

open Complex DirichletCharacter

/-- The precise core theorem used by the submitted project's endpoints. -/
def EveryCharacter : Prop :=
  ∀ (N : ℕ) [NeZero N] (χ : DirichletCharacter ℂ N) (s : ℂ),
    1 / 2 < s.re → (χ ≠ 1 ∨ s ≠ 1) → LFunction χ s ≠ 0

/-- Its specialization to the Riemann zeta function. -/
def ZetaRightNonvanishing : Prop :=
  ∀ s : ℂ, 1 / 2 < s.re → s ≠ 1 → riemannZeta s ≠ 0

theorem zeta_right_of_every (h : EveryCharacter) : ZetaRightNonvanishing := by
  intro s hs hs1
  have hL := h 1 (1 : DirichletCharacter ℂ 1) s hs (Or.inr hs1)
  rwa [LFunction_modOne_eq] at hL

/-- Nontrivial zeta zeros do not meet the zero-assigned poles of Gamma_R. -/
theorem gammaR_ne_zero_of_nontrivial (s : ℂ) (hs0 : s ≠ 0)
    (htriv : ¬ ∃ n : ℕ, s = -2 * (n + 1)) : Gammaℝ s ≠ 0 := by
  intro hG
  obtain ⟨n, hn⟩ := Complex.Gammaℝ_eq_zero_iff.mp hG
  cases n with
  | zero =>
      apply hs0
      simpa only [Nat.cast_zero, mul_zero, neg_zero] using hn
  | succ n =>
      apply htriv
      refine ⟨n, ?_⟩
      simpa only [Nat.cast_succ, neg_mul] using hn

/-- This is a CONDITIONAL reduction, with the right half-plane theorem as input. -/
theorem rh_of_right (hz : ZetaRightNonvanishing) : RiemannHypothesis := by
  intro s hs htriv hs1
  rcases lt_trichotomy s.re (1 / 2) with hlt | heq | hgt
  · exfalso
    have hs0 : s ≠ 0 := by
      rintro rfl
      rw [riemannZeta_zero] at hs
      norm_num at hs
    have ht : 1 / 2 < (1 - s).re := by
      rw [Complex.sub_re, Complex.one_re]
      linarith
    have ht1 : 1 - s ≠ 1 := fun e => hs0 (sub_eq_self.mp e)
    have ht0 : 1 - s ≠ 0 := sub_ne_zero.mpr hs1.symm
    have hG := gammaR_ne_zero_of_nontrivial s hs0 htriv
    have hc : completedRiemannZeta s = 0 := by
      rw [riemannZeta_def_of_ne_zero hs0, div_eq_zero_iff] at hs
      exact hs.resolve_right hG
    have hzt : riemannZeta (1 - s) = 0 := by
      rw [riemannZeta_def_of_ne_zero ht0, completedRiemannZeta_one_sub, hc, zero_div]
    exact hz (1 - s) ht ht1 hzt
  · exact heq
  · exact hz s hgt hs1 hs |>.elim

/-- The parameter h remains in the theorem type; it is not proved in this file. -/
theorem rh_of_every (h : EveryCharacter) : RiemannHypothesis :=
  rh_of_right (zeta_right_of_every h)

theorem gamma_factor_ne_zero {N : ℕ} (χ : DirichletCharacter ℂ N) {s : ℂ}
    (hs : 0 < s.re) : gammaFactor χ s ≠ 0 := by
  rcases χ.even_or_odd with h | h
  · rw [h.gammaFactor_def]
    exact Gammaℝ_ne_zero_of_re_pos hs
  · rw [h.gammaFactor_def]
    exact Gammaℝ_ne_zero_of_re_pos (by rw [add_re, one_re]; linarith)

theorem primitive_reflect {N : ℕ} [NeZero N] (χ : DirichletCharacter ℂ N)
    (hχ : χ.IsPrimitive) {s : ℂ} (h0 : 0 < s.re) (h1 : s.re < 1)
    (hz : LFunction χ s = 0) : LFunction χ⁻¹ (1 - s) = 0 := by
  have hs0 : s ≠ 0 := fun e => by simp [e] at h0
  have hs1 : s ≠ 1 := fun e => by simp [e] at h1
  have hinv : χ⁻¹.IsPrimitive := by
    rw [isPrimitive_def, conductor_inv]
    exact hχ
  have hc : completedLFunction χ s = 0 := by
    rw [LFunction_eq_completed_div_gammaFactor χ s (Or.inl hs0)] at hz
    exact (div_eq_zero_iff.mp hz).resolve_right (gamma_factor_ne_zero χ h0)
  have hfe := hinv.completedLFunction_one_sub s
  rw [inv_inv, hc, mul_zero] at hfe
  have ht0 : 1 - s ≠ 0 := sub_ne_zero.mpr hs1.symm
  rw [LFunction_eq_completed_div_gammaFactor χ⁻¹ (1 - s) (Or.inl ht0), hfe, zero_div]

theorem primitive_crit_line (h : EveryCharacter) {N : ℕ} [NeZero N]
    (χ : DirichletCharacter ℂ N) (hχ : χ.IsPrimitive) {s : ℂ}
    (h0 : 0 < s.re) (h1 : s.re < 1) (hz : LFunction χ s = 0) : s.re = 1 / 2 := by
  have hs0 : s ≠ 0 := fun e => by simp [e] at h0
  have hs1 : s ≠ 1 := fun e => by simp [e] at h1
  rcases lt_trichotomy s.re (1 / 2) with hlt | heq | hgt
  · exfalso
    have ht : 1 / 2 < (1 - s).re := by
      rw [Complex.sub_re, Complex.one_re]
      linarith
    have ht1 : 1 - s ≠ 1 := fun e => hs0 (sub_eq_self.mp e)
    exact h N χ⁻¹ (1 - s) ht (Or.inr ht1) (primitive_reflect χ hχ h0 h1 hz)
  · exact heq
  · exact h N χ s hgt (Or.inr hs1) hz |>.elim

/-- Finite Euler factors have no zero in Re(s) > 0. -/
theorem euler_factor_ne_zero {M : ℕ} (ψ : DirichletCharacter ℂ M) {s : ℂ}
    (hs : 0 < s.re) (p : ℕ) (hp : p.Prime) :
    (1 : ℂ) - ψ p * (p : ℂ) ^ (-s) ≠ 0 := by
  intro h
  have h1 : ψ p * (p : ℂ) ^ (-s) = 1 := (sub_eq_zero.mp h).symm
  have hp1 : (1 : ℝ) < p := by exact_mod_cast hp.one_lt
  have hpow : ‖(p : ℂ) ^ (-s)‖ < 1 := by
    rw [Complex.norm_natCast_cpow_of_pos hp.pos, Complex.neg_re]
    exact Real.rpow_lt_one_of_one_lt_of_neg hp1 (by linarith)
  have hn : ‖ψ p * (p : ℂ) ^ (-s)‖ < 1 := by
    rw [norm_mul]
    calc
      ‖ψ p‖ * ‖(p : ℂ) ^ (-s)‖ ≤ 1 * ‖(p : ℂ) ^ (-s)‖ :=
        mul_le_mul_of_nonneg_right (ψ.norm_le_one _) (norm_nonneg _)
      _ < 1 := by simpa only [one_mul] using hpow
  rw [h1, norm_one] at hn
  exact lt_irrefl _ hn

theorem primitive_zero {N : ℕ} [NeZero N] (χ : DirichletCharacter ℂ N)
    [NeZero χ.conductor] {s : ℂ} (h0 : 0 < s.re) (h1 : s.re < 1)
    (hz : LFunction χ s = 0) : LFunction χ.primitiveCharacter s = 0 := by
  have hs1 : s ≠ 1 := fun e => by simp [e] at h1
  have key := LFunction_changeLevel χ.conductor_dvd_level χ.primitiveCharacter (Or.inr hs1)
  rw [χ.changeLevel_primitiveCharacter, hz] at key
  rcases mul_eq_zero.mp key.symm with hzero | hprod
  · exact hzero
  · obtain ⟨p, hp, hp0⟩ := Finset.prod_eq_zero_iff.mp hprod
    exact (euler_factor_ne_zero _ h0 p (Nat.prime_of_mem_primeFactors hp) hp0).elim

theorem dirichlet_crit_line (h : EveryCharacter) {N : ℕ} [NeZero N]
    (χ : DirichletCharacter ℂ N) {s : ℂ} (h0 : 0 < s.re) (h1 : s.re < 1)
    (hz : LFunction χ s = 0) : s.re = 1 / 2 := by
  haveI : NeZero χ.conductor := ⟨χ.conductor_ne_zero⟩
  exact primitive_crit_line h χ.primitiveCharacter χ.primitiveCharacter_isPrimitive
    h0 h1 (primitive_zero χ h0 h1 hz)

#print axioms rh_of_right
#print axioms rh_of_every
#print axioms primitive_crit_line
#print axioms dirichlet_crit_line

end EndpointReduction
