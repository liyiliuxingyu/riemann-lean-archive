/-
Independent expected interface for the five public archive theorems.

This module imports only the two named official Mathlib modules. In particular,
it must be compiled without
importing Main, New, Lib, or any proof module from the candidate project.
Its four formulas reproduce the archived Statements.lean (Git blob
1cd1bce93344065936b2b392b23306254e0785ef), with explicit root-qualified
mathematical constants and a separate namespace to prevent name collisions.

Compilation establishes these formulas in the selected Mathlib environment;
it does not itself establish any Riemann-hypothesis theorem.
-/
import Mathlib.NumberTheory.LSeries.DirichletContinuation
import Mathlib.NumberTheory.LSeries.RiemannZeta

set_option autoImplicit false
set_option relaxedAutoImplicit false

namespace ArchiveExpected

def RiemannZetaZerosOnLine : Prop :=
  ∀ s : _root_.Complex, _root_.riemannZeta s = 0 →
    (¬ ∃ n : ℕ, s = -2 * ((n : _root_.Complex) + 1)) →
    s ≠ 1 → s.re = 1 / 2

def DirichletLNonvanishingRightOfHalf : Prop :=
  ∀ (N : ℕ) [_root_.NeZero N] (χ : _root_.DirichletCharacter _root_.Complex N)
    (s : _root_.Complex), 1 / 2 < s.re → (χ ≠ 1 ∨ s ≠ 1) →
    _root_.DirichletCharacter.LFunction χ s ≠ 0

def DirichletLZerosOnLine : Prop :=
  ∀ (N : ℕ) [_root_.NeZero N] (χ : _root_.DirichletCharacter _root_.Complex N)
    (s : _root_.Complex), 0 < s.re → s.re < 1 →
    _root_.DirichletCharacter.LFunction χ s = 0 → s.re = 1 / 2

def PrimitiveDirichletLZerosOnLine : Prop :=
  ∀ (N : ℕ) [_root_.NeZero N] (χ : _root_.DirichletCharacter _root_.Complex N),
    _root_.DirichletCharacter.IsPrimitive χ →
    ∀ s : _root_.Complex, 0 < s.re → s.re < 1 →
      _root_.DirichletCharacter.LFunction χ s = 0 → s.re = 1 / 2

/-- The explicit archived zeta statement is definitionally the Mathlib RH statement. -/
theorem zeta_statement_eq_mathlib :
    RiemannZetaZerosOnLine = _root_.RiemannHypothesis := rfl

/-- A logical specialization only: its premise is explicit and is not proved here. -/
theorem primitive_of_all (h : DirichletLZerosOnLine) : PrimitiveDirichletLZerosOnLine :=
  fun N _ χ _ ↦ h N χ

end ArchiveExpected
