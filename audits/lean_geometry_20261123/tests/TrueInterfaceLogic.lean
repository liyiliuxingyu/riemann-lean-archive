/-
An independent, core-only illustration. This does not compile or prove the RH
project. It distinguishes a trivial intermediate predicate from an invalid
inference to an independently fixed nontrivial target.
-/

namespace TrueInterfaceLogic

def anyGeometry (_ : Nat) : Prop := True
def realGeometry (n : Nat) : Prop := n = 0

theorem anyGeometry_holds (n : Nat) : anyGeometry n := True.intro

/-- A universal bridge to the stronger predicate does not follow from True. -/
theorem no_automatic_geometry_bridge :
    ¬ (∀ n : Nat, anyGeometry n → realGeometry n) := by
  intro bridge
  exact Nat.noConfusion (bridge 1 True.intro)

/-- Supplying a proof of True -> P already supplies the essential proof of P. -/
theorem true_imp_iff (P : Prop) : (True → P) ↔ P :=
  ⟨fun f => f True.intro, fun p _ => p⟩

theorem true_does_not_imply_false : ¬ (True → False) :=
  fun f => f True.intro

structure Hypotheses (geometry : Nat → Prop) where
  n : Nat
  geometricCondition : geometry n
  positive : 0 < n

/-- The nontrivial field remains an obligation for every geometry parameter. -/
theorem positive_from_bundle (geometry : Nat → Prop) (h : Hypotheses geometry) :
    0 < h.n := h.positive

def concreteBundle : Hypotheses anyGeometry where
  n := 1
  geometricCondition := True.intro
  positive := Nat.zero_lt_succ 0

/-- The proof uses anyGeometry, but the independently fixed target is honest. -/
theorem fixed_arithmetic_target : (0 : Nat) < 1 :=
  positive_from_bundle anyGeometry concreteBundle

#print axioms no_automatic_geometry_bridge
#print axioms true_imp_iff
#print axioms true_does_not_imply_false
#print axioms fixed_arithmetic_target

end TrueInterfaceLogic
