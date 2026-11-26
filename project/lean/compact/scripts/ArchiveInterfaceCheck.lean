/-
Acceptance check for the five public declarations, in the pinned candidate
Lean/Mathlib environment. ArchiveExpectedStatements must first be compiled
independently with its two official Mathlib imports and no candidate proof module.

Passing this file shows the five compiled exports have the archived formulas in
this environment, have no added theorem/universe parameters, and use no axiom
outside propext, Classical.choice, Quot.sound. It is not a cross-version proof
that the complete Lean 4.33.1 and Lean 4.35.0 environments are equivalent.
-/
import ArchiveExpectedStatements
import ArchiveInterfaceAudit
import Main

set_option autoImplicit false
set_option relaxedAutoImplicit false

namespace ArchiveInterfaceCheck

theorem checked_riemannHypothesis : ArchiveExpected.RiemannZetaZerosOnLine :=
  _root_.riemannHypothesis

theorem checked_riemannZeta_eq_zero_re : ArchiveExpected.RiemannZetaZerosOnLine :=
  _root_.riemannZeta_eq_zero_re

theorem checked_LFunction_ne_zero_of_half_lt_re :
    ArchiveExpected.DirichletLNonvanishingRightOfHalf :=
  _root_.LFunction_ne_zero_of_half_lt_re

theorem checked_LFunction_eq_zero_re : ArchiveExpected.DirichletLZerosOnLine :=
  _root_.LFunction_eq_zero_re

theorem checked_LFunction_eq_zero_re_of_isPrimitive :
    ArchiveExpected.PrimitiveDirichletLZerosOnLine :=
  _root_.LFunction_eq_zero_re_of_isPrimitive

end ArchiveInterfaceCheck

open Lean Elab Command in
run_cmd liftTermElabM do
  let targets : List (Name × Name) := [
    (.mkSimple "riemannHypothesis", ``ArchiveExpected.RiemannZetaZerosOnLine),
    (.mkSimple "riemannZeta_eq_zero_re", ``ArchiveExpected.RiemannZetaZerosOnLine),
    (.mkSimple "LFunction_ne_zero_of_half_lt_re", ``ArchiveExpected.DirichletLNonvanishingRightOfHalf),
    (.mkSimple "LFunction_eq_zero_re", ``ArchiveExpected.DirichletLZerosOnLine),
    (.mkSimple "LFunction_eq_zero_re_of_isPrimitive", ``ArchiveExpected.PrimitiveDirichletLZerosOnLine)]
  for (actual, expected) in targets do
    ArchiveInterfaceAudit.check actual expected

#print axioms ArchiveInterfaceCheck.checked_riemannHypothesis
#print axioms ArchiveInterfaceCheck.checked_riemannZeta_eq_zero_re
#print axioms ArchiveInterfaceCheck.checked_LFunction_ne_zero_of_half_lt_re
#print axioms ArchiveInterfaceCheck.checked_LFunction_eq_zero_re
#print axioms ArchiveInterfaceCheck.checked_LFunction_eq_zero_re_of_isPrimitive
