import Mathlib.Topology.Algebra.Module.Basic

set_option autoImplicit false
set_option relaxedAutoImplicit false

namespace ReciprocityTheory.Gal

variable {R : Type*} [CommRing R]
variable {M : Type*} [AddCommGroup M] [Module R M] [TopologicalSpace M]
  [IsTopologicalAddGroup M] [ContinuousConstSMul R M]
variable (Mplus : Submodule R M)

theorem continuous_mkQ : Continuous (Mplus.mkQ) :=
  (Submodule.isQuotientMap_mkQ Mplus).continuous

end ReciprocityTheory.Gal

#print axioms ReciprocityTheory.Gal.continuous_mkQ
