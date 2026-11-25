/-
Run only inside the original project after its exact dependencies and modules
have actually been built. This file is an audit request, not a stored audit
result. Its existence does NOT show that Main compiled or that the resulting
axiom list is safe. Preserve the actual Lean stdout, stderr, exit status and
toolchain/dependency revisions when it is run.

Main is a module name. Its five public theorems are ROOT declarations, not
members of a namespace named Main.
-/
import Main

#print _root_.RiemannHypothesis
#print _root_.RiemannZetaZerosOnLine
#print _root_.DirichletLNonvanishingRightOfHalf
#print _root_.DirichletLZerosOnLine
#print _root_.PrimitiveDirichletLZerosOnLine

#check _root_.riemannHypothesis
#check _root_.riemannZeta_eq_zero_re
#check _root_.LFunction_ne_zero_of_half_lt_re
#check _root_.LFunction_eq_zero_re
#check _root_.LFunction_eq_zero_re_of_isPrimitive

#print _root_.riemannHypothesis
#print _root_.riemannZeta_eq_zero_re
#print _root_.LFunction_ne_zero_of_half_lt_re
#print _root_.LFunction_eq_zero_re
#print _root_.LFunction_eq_zero_re_of_isPrimitive

#print axioms _root_.riemannHypothesis
#print axioms _root_.riemannZeta_eq_zero_re
#print axioms _root_.LFunction_ne_zero_of_half_lt_re
#print axioms _root_.LFunction_eq_zero_re
#print axioms _root_.LFunction_eq_zero_re_of_isPrimitive

namespace FullProjectAxiomsAudit

/-- The zero formulation must be definitionally the pinned Mathlib target. -/
theorem advertised_zeta_statement_eq_mathlib :
    _root_.RiemannZetaZerosOnLine = _root_.RiemannHypothesis := rfl

/-- Direct elaboration checks the exact theorem types, without helper tactics. -/
theorem root_rh_has_expected_type : _root_.RiemannHypothesis :=
  _root_.riemannHypothesis

theorem root_zeta_has_expected_type :
    ∀ s : ℂ, _root_.riemannZeta s = 0 →
      (¬∃ n : ℕ, s = -2 * ((n : ℂ) + 1)) → s ≠ 1 → s.re = 1 / 2 :=
  _root_.riemannZeta_eq_zero_re

theorem root_nonvanishing_has_expected_type :
    ∀ (N : ℕ) [NeZero N] (χ : _root_.DirichletCharacter ℂ N) (s : ℂ),
      1 / 2 < s.re → (χ ≠ 1 ∨ s ≠ 1) →
        _root_.DirichletCharacter.LFunction χ s ≠ 0 :=
  _root_.LFunction_ne_zero_of_half_lt_re

theorem root_strip_has_expected_type :
    ∀ (N : ℕ) [NeZero N] (χ : _root_.DirichletCharacter ℂ N) (s : ℂ),
      0 < s.re → s.re < 1 → _root_.DirichletCharacter.LFunction χ s = 0 →
        s.re = 1 / 2 :=
  _root_.LFunction_eq_zero_re

theorem root_primitive_has_expected_type :
    ∀ (N : ℕ) [NeZero N] (χ : _root_.DirichletCharacter ℂ N), χ.IsPrimitive →
      ∀ s : ℂ, 0 < s.re → s.re < 1 →
        _root_.DirichletCharacter.LFunction χ s = 0 → s.re = 1 / 2 :=
  _root_.LFunction_eq_zero_re_of_isPrimitive

#print axioms root_rh_has_expected_type
#print axioms root_zeta_has_expected_type
#print axioms root_nonvanishing_has_expected_type
#print axioms root_strip_has_expected_type
#print axioms root_primitive_has_expected_type

end FullProjectAxiomsAudit
