import Init

-- A proof parameter is an explicit hypothesis, not an extra kernel axiom.
theorem conditional (P : Prop) (h : P) : P := h

#check conditional
#print axioms conditional
