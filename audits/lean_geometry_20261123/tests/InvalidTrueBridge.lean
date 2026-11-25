/- This intentionally fails. It is a negative test, not project source. -/

def anyGeometry (_ : Nat) : Prop := True
def realGeometry (n : Nat) : Prop := n = 0

theorem invalid_bridge : realGeometry 1 := by
  exact (show anyGeometry 1 from True.intro)
