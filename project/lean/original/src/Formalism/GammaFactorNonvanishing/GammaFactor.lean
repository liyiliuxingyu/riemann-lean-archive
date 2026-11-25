import Mathlib.NumberTheory.LSeries.DirichletContinuation

open Complex DirichletCharacter

theorem Formalism.VW.gammaFactor_ne_zero {N : ℕ} (χ : DirichletCharacter ℂ N) {s : ℂ} (hs : 0 < s.re) : gammaFactor χ s ≠ 0 := by
  rcases χ.even_or_odd with h | h
  · rw [h.gammaFactor_def]; exact Gammaℝ_ne_zero_of_re_pos hs
  · rw [h.gammaFactor_def]
    exact Gammaℝ_ne_zero_of_re_pos (by rw [add_re, one_re]; exact add_pos hs zero_lt_one)
