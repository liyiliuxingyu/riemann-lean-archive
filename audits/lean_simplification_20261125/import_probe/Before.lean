import Init
import Init
import Std
import Std

set_option autoImplicit false

theorem duplicate_import_probe (n : Nat) : n + 0 = n := Nat.add_zero n

#print duplicate_import_probe
#print axioms duplicate_import_probe
