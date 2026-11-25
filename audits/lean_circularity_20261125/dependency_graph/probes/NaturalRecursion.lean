import Init

-- Each recursive call uses the strictly smaller natural-number argument.
theorem naturalRecursion (n : Nat) : n = n := by
  cases n with
  | zero => rfl
  | succ m => exact congrArg Nat.succ (naturalRecursion m)
termination_by n

#check naturalRecursion
#print axioms naturalRecursion
