/-
Purpose: check only the meanings of the advertised statements against pinned
Mathlib. This file does NOT import Main or the submitted project, and it does
NOT prove RiemannHypothesis or the Dirichlet nonvanishing statements.

The four definitions below reproduce src/Statements.lean verbatim, inside an
audit-only namespace to avoid confusing them with project declarations.

Intended environment: Lean v4.33.1 and mathlib4 revision
0df444a360eaa60ab8c11dca51a86af692955474.
Successful compilation would certify only these statement-level comparisons.
-/
-- Audit-only imports narrowed to the two pinned Mathlib modules used by these statements.
import Mathlib.NumberTheory.LSeries.RiemannZeta
import Mathlib.NumberTheory.LSeries.DirichletContinuation

namespace StatementSemanticsAudit

def RiemannZetaZerosOnLine : Prop :=
  ∀ s : ℂ, riemannZeta s = 0 → (¬∃ n : ℕ, s = -2 * ((n : ℂ) + 1)) → s ≠ 1 → s.re = 1 / 2

def DirichletLNonvanishingRightOfHalf : Prop :=
  ∀ (N : ℕ) [NeZero N] (χ : DirichletCharacter ℂ N) (s : ℂ),
    1 / 2 < s.re → (χ ≠ 1 ∨ s ≠ 1) → DirichletCharacter.LFunction χ s ≠ 0

def DirichletLZerosOnLine : Prop :=
  ∀ (N : ℕ) [NeZero N] (χ : DirichletCharacter ℂ N) (s : ℂ),
    0 < s.re → s.re < 1 → DirichletCharacter.LFunction χ s = 0 → s.re = 1 / 2

def PrimitiveDirichletLZerosOnLine : Prop :=
  ∀ (N : ℕ) [NeZero N] (χ : DirichletCharacter ℂ N), χ.IsPrimitive →
    ∀ s : ℂ, 0 < s.re → s.re < 1 → DirichletCharacter.LFunction χ s = 0 → s.re = 1 / 2

/-- This proves an equality of propositions, not either proposition. -/
theorem advertised_zeta_statement_eq_mathlib :
    RiemannZetaZerosOnLine = _root_.RiemannHypothesis := rfl

theorem advertised_zeta_statement_iff_mathlib :
    RiemannZetaZerosOnLine ↔ _root_.RiemannHypothesis := Iff.rfl

/-- Explicitly pin the zeta symbol to the Mathlib root declaration. -/
theorem advertised_zeta_symbol_is_root :
    RiemannZetaZerosOnLine =
      (∀ s : ℂ, _root_.riemannZeta s = 0 →
        (¬∃ n : ℕ, s = -2 * ((n : ℂ) + 1)) → s ≠ 1 → s.re = 1 / 2) := rfl

/-- Explicitly pin the L-function symbol to the Mathlib root declaration. -/
theorem advertised_dirichlet_symbol_is_root :
    DirichletLNonvanishingRightOfHalf =
      (∀ (N : ℕ) [NeZero N] (χ : _root_.DirichletCharacter ℂ N) (s : ℂ),
        1 / 2 < s.re → (χ ≠ 1 ∨ s ≠ 1) →
          _root_.DirichletCharacter.LFunction χ s ≠ 0) := rfl

#print _root_.RiemannHypothesis
#print _root_.riemannZeta
#check _root_.DirichletCharacter.LFunction
#print advertised_zeta_statement_eq_mathlib
#print advertised_zeta_statement_iff_mathlib
#print axioms advertised_zeta_statement_eq_mathlib
#print axioms advertised_zeta_statement_iff_mathlib
#print axioms advertised_zeta_symbol_is_root
#print axioms advertised_dirichlet_symbol_is_root

end StatementSemanticsAudit
