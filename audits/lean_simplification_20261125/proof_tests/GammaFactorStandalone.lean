import Mathlib.NumberTheory.LSeries.DirichletContinuation

open Complex DirichletCharacter

theorem Formalism.VW.gammaFactor_ne_zero {N : ℕ} (χ : DirichletCharacter ℂ N) {s : ℂ} (hs : 0 < s.re) : gammaFactor χ s ≠ 0 := by
  rcases χ.even_or_odd with h | h
  · rw [h.gammaFactor_def]; exact Gammaℝ_ne_zero_of_re_pos hs
  · rw [h.gammaFactor_def]
    exact Gammaℝ_ne_zero_of_re_pos (by rw [add_re, one_re]; exact add_pos hs zero_lt_one)

namespace Claim

theorem gamma_ne_zero {M : ℕ} [NeZero M] (φ : DirichletCharacter ℂ M) {t : ℂ} (ht : 0 < t.re) :
    DirichletCharacter.gammaFactor φ t ≠ 0 :=
  Formalism.VW.gammaFactor_ne_zero φ ht

end Claim

namespace GlobalTheory.Mem.An

section
variable {q : ℕ}

theorem zsym_gammaFactor_ne_zero (χ : DirichletCharacter ℂ q) {s : ℂ} (hs : 0 < s.re) :
    χ.gammaFactor s ≠ 0 :=
  Formalism.VW.gammaFactor_ne_zero χ hs

end

end GlobalTheory.Mem.An

example : ∀ {N : ℕ} (χ : DirichletCharacter ℂ N) {s : ℂ},
    0 < s.re → gammaFactor χ s ≠ 0 := @Formalism.VW.gammaFactor_ne_zero

example : ∀ {M : ℕ} [NeZero M] (φ : DirichletCharacter ℂ M) {t : ℂ},
    0 < t.re → gammaFactor φ t ≠ 0 := @Claim.gamma_ne_zero

example : ∀ {q : ℕ} (χ : DirichletCharacter ℂ q) {s : ℂ},
    0 < s.re → gammaFactor χ s ≠ 0 := @GlobalTheory.Mem.An.zsym_gammaFactor_ne_zero

#print axioms Formalism.VW.gammaFactor_ne_zero
#print axioms Claim.gamma_ne_zero
#print axioms GlobalTheory.Mem.An.zsym_gammaFactor_ne_zero
