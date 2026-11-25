/-
An entry point to be used INSIDE the original, fully built Lean project.
This imports the original proof; it is not the all-source bundle and does not
replace the original project's modules or Mathlib dependencies.
Local compilation of this entry has not yet been performed in this workspace.
-/
import Main

namespace HumanReadableRH

/-- The public theorem exported by the original Main.lean. -/
theorem riemannHypothesisFromOriginal : RiemannHypothesis := by
  exact _root_.riemannHypothesis

#check riemannHypothesisFromOriginal
#print axioms riemannHypothesisFromOriginal

end HumanReadableRH
