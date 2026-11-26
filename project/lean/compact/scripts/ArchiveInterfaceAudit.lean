/-
Read-only elaboration-time acceptance checks. This module defines no proof axiom
and imports no submitted mathematical proof. The kernel-checked assignments in
ArchiveInterfaceCheck.lean complement these metadata checks.
-/
import Lean

set_option autoImplicit false

open Lean Meta

namespace ArchiveInterfaceAudit

/-- Collect binder visibility after unfolding aliases at the head of a type. -/
private partial def binderKinds (type : Expr) : MetaM (Array BinderInfo) := do
  let type ← whnf type
  match type with
  | .forallE name domain body info =>
      withLocalDecl name info domain fun value => do
        return #[info] ++ (← binderKinds (body.instantiate1 value))
  | _ => return #[]

/-- Require the actual root declaration to have exactly the expected closed type. -/
def check (actualName expectedName : Name) : MetaM Unit := do
  let actual ← getConstInfo actualName
  match actual with
  | .thmInfo _ => pure ()
  | _ => throwError "Expected a theorem declaration at {actualName}"
  unless actual.levelParams.isEmpty do
    throwError "Unexpected universe parameters on {actualName}"
  if actual.type.hasMVar then
    throwError "Unresolved metavariable in the type of {actualName}"
  let expected ← getConstInfo expectedName
  match expected with
  | .defnInfo _ => pure ()
  | _ => throwError "Expected interface must be a proposition-valued definition"
  unless expected.levelParams.isEmpty do
    throwError "Expected interface must not have universe parameters"
  unless expected.type == mkSort .zero do
    throwError "Expected interface must have type Prop"
  let expectedType := mkConst expectedName
  withTransparency .all do
    unless ← isDefEq actual.type expectedType do
      throwError "Type mismatch for {actualName}; expected {expectedName}"
    let actualBinders ← binderKinds actual.type
    let expectedBinders ← binderKinds expectedType
    unless actualBinders == expectedBinders do
      throwError "Binder visibility mismatch for {actualName}"
  let allowed : Array Name := #[``propext, ``Classical.choice, ``Quot.sound]
  let axioms ← collectAxioms actualName
  for axiomName in axioms do
    unless allowed.contains axiomName do
      throwError "Disallowed axiom {axiomName} in {actualName}"
  logInfo m!"INTERFACE_OK {actualName}; expected={expectedName}; axioms={axioms}"

end ArchiveInterfaceAudit
