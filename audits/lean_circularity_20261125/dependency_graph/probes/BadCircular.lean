import Init

-- The recursive call has no decreasing argument or proof of P.
theorem badCircular (P : Prop) : P := badCircular P
