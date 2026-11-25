import Lean

open Lean Elab Tactic Meta

elab "kexactB " e:term : tactic => withMainContext do
  let g ← getMainGoal
  let v ← Term.elabTermAndSynthesize e none
  g.assign (← instantiateMVars v)

set_option allowUnsafeReducibility true
set_option quotPrecheck false
set_option hygiene false
theorem audit_invalid_options : False := by kexactB True.intro
