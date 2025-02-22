## used as a namespace, so avoid filling it with lower-level objects
from . import treeoperations as _to
from . import treeproxies as _tp

from .root import loadBambooExtensions
loadBambooExtensions()

import logging
_logger = logging.getLogger(__name__)

## simple type support
def c_bool(arg):
    """ Construct a boolean constant """
    if arg:
        return _tp.makeProxy(_tp.boolType, _to.Const(_tp.boolType, "true"))
    else:
        return _tp.makeProxy(_tp.boolType, _to.Const(_tp.boolType, "false"))
def c_int(num, typeName="Int_t"):
    """ Construct an integer number constant """
    return _tp.makeConst(num, typeName)
def c_float(num, typeName="Float_t"):
    """ Construct a floating-point number constant """
    return _tp.makeConst(num, typeName)

## boolean logic
def NOT(sth):
    """ Logical NOT """
    return _to.MathOp("not", _to.adaptArg(sth, _tp.boolType), outType=_tp.boolType).result
def AND(*args):
    """ Logical AND """
    if len(args) == 1:
        return _tp.makeProxy(_tp.boolType, _to.adaptArg(args[0], _tp.boolType))
    else:
        return _to.MathOp("and", *[ _to.adaptArg(arg, _tp.boolType) for arg in args ], outType=_tp.boolType).result
def OR(*args):
    """ Logical OR """
    if len(args) == 1:
        return _tp.makeProxy(_tp.boolType, _to.adaptArg(args[0], _tp.boolType))
    else:
        return _to.MathOp("or", *[ _to.adaptArg(arg, _tp.boolType) for arg in args ], outType=_tp.boolType).result
def switch(test, trueBranch, falseBranch, checkTypes=True):
    """ Pick one or another value, based on a third one (ternary operator in C++)

    :Example:

    >>> op.switch(runOnMC, mySF, 1.) ## incomplete pseudocode
    """
    if checkTypes:
        aType = trueBranch._typeName
        bType = falseBranch._typeName
        if aType != bType:
            if not any(aType in typeGroup and bType in typeGroup for typeGroup in (_tp._boolTypes, _tp._integerTypes, _tp._floatTypes)):
                _logger.warning(f"Possibly incompatible types: {aType} and {bType}")
    return _to.MathOp("switch", test, trueBranch, falseBranch, outType=trueBranch._typeName).result
def multiSwitch(*args):
    """ Construct arbitrary-length switch (if-elif-elif-...-else sequence)

    :Example:

    >>> op.multiSwitch((lepton.pt > 30, 4.), (lepton.pt > 15 && op.abs(lepton.eta) < 2.1, 5.), 3.)

    is equivalent to:

    >>> if lepton.pt > 30:
    >>>     return 5.
    >>> elif lepton.pt > 15 and abs(lepton.eta) < 2.1:
    >>>     return 4.
    >>> else:
    >>>     return 3.
    """
    if len(args) == 1:
        return args[0]
    else:
        return switch(args[0][0], args[0][1], multiSwitch(*(args[1:])))
def extMethod(name, returnType=None):
    """ Retrieve a (non-member) C(++) method

    :param name: name of the method
    :param returnType: return type (otherwise deduced by introspection)

    :returns: a method proxy, that can be called and returns a value decorated as the return type of the method

    :Example:

    >>> phi_0_2pi = op.extMethod("ROOT::Math::VectorUtil::Phi_0_2pi")
    >>> dphi_2pi = phi_0_2pi(a.Phi()-b.Phi())
    """
    return _tp.MethodProxy(name, returnType=returnType) ## TODO somehow take care of includes as well
def extVar(typeName, name):
    return _to.ExtVar(typeName, name).result
def construct(typeName, args):
    if not hasattr(args, "__iter__"):
        args = (args,)
    return _to.Construct(typeName, args).result
def static_cast(typeName, arg):
    return _tp.makeProxy(typeName, _to.CallMethod("static_cast<{0}>".format(typeName), (arg,), getFromRoot=False))
def initList(typeName, elmName, elms):
    return _to.InitList(typeName, elms, elmType=elmName).result
def define(typeName, definition, nameHint=None):
    """ Define a variable as a symbol with the interpreter

    :param typeName: result type name
    :param definition: C++ definition string, with ``<<name>>`` instead of the variable name (which will be replaced by nameHint or a unique name)
    :param nameHint: (optional) name for the variable

    .. caution::

        nameHint (if given) should be unique (for the sample), otherwise an exception will be thrown
    """
    return _to.DefinedSymbol(typeName, definition, nameHint=nameHint).result
def defineOnFirstUse(sth):
    """
    Construct an expression that will be precalculated (with an RDataFrame::Define node) when first used

    This may be useful for expensive function calls, and should prevent double work in most cases.
    Sometimes it is useful to explicitly insert the Define node explicitly, in that case
    :py:func:`bamboo.analysisutils.forceDefine` can be used.
    """
    arg = _to.adaptArg(sth)
    if isinstance(arg, _to.DefineOnFirstUse):
        return sth
    else:
        return _to.DefineOnFirstUse(arg).result

## math
def abs(sth):
    """ Return the absolute value

    :Example:

    >>> op.abs(t.Muon[0].p4.Eta())
    """
    return _to.MathOp("abs", sth, outType=sth._typeName).result
def sign(sth):
    """ Return the sign of a number

    :Example:

    >>> op.sign(t.Muon[0].p4.Eta())
    """
    return switch(sth!=0., extMethod("std::lround", returnType="long")(sth/abs(sth)), c_int(0, typeName="long"))
def sum(*args, **kwargs):
    """ Return the sum of the arguments

    :Example:

    >>> op.sum(t.Muon[0].p4.Eta(), t.Muon[1].p4.Eta())
    """
    return _to.MathOp("add", *args, outType=kwargs.pop("outType",
        _tp.floatType if _tp._hasFloat(*args) else _tp.intType)).result
def product(*args):
    """ Return the product of the arguments

    :Example:

    >>> op.product(t.Muon[0].p4.Eta(), t.Muon[1].p4.Eta())
    """
    return _to.MathOp("multiply", *args,
            outType=(_tp.floatType if _tp._hasFloat(*args) else _tp.intType)).result
def sqrt(sth):
    """ Return the square root of a number

    :Example:

    >>> m1, m2 = t.Muon[0].p4, t.Muon[1].p4
    >>> m12dR = op.sqrt( op.pow(m1.Eta()-m2.Eta(), 2) + op.pow(m1.Phi()-m2.Phi(), 2) )
    """
    return _to.MathOp("sqrt", sth, outType=sth._typeName).result
def pow(base, exp):
    """ Return a power of a number

    :Example:

    >>> m1, m2 = t.Muon[0].p4, t.Muon[1].p4
    >>> m12dR = op.sqrt( op.pow(m1.Eta()-m2.Eta(), 2) + op.pow(m1.Phi()-m2.Phi(), 2) )
    """
    return _to.MathOp("pow", base, exp, outType=base._typeName).result
def exp(sth):
    """ Return the exponential of a number

    :Example:

    >>> op.exp(op.abs(t.Muon[0].p4.Eta()))
    """
    return _to.MathOp("exp", sth).result
def log(sth):
    """ Return the natural logarithm of a number

    :Example:

    >>> op.log(t.Muon[0].p4.Pt())
    """
    return _to.MathOp("log", sth).result
def log10(sth):
    """ Return the base-10 logarithm of a number

    :Example:

    >>> op.log10(t.Muon[0].p4.Pt())
    """
    return _to.MathOp("log10", sth).result

def sin(sth):
    """ Return the sine of a number

    :Example:

    >>> op.sin(t.Muon[0].p4.Phi())
    """
    return _to.MathOp("sin", sth).result

def cos(sth):
    """ Return the cosine of a number

    :Example:

    >>> op.cos(t.Muon[0].p4.Phi())
    """
    return _to.MathOp("cos", sth).result

def tan(sth):
    """ Return the tangent of a number

    :Example:

    >>> op.tan(t.Muon[0].p4.Phi())
    """
    return _to.MathOp("tan", sth).result

def asin(sth):
    """ Return the arcsine of a number

    :Example:

    >>> op.asin(op.c_float(3.1415))
    """
    return _to.MathOp("asin", sth).result

def acos(sth):
    """ Return the arccosine of a number

    :Example:

    >>> op.ascos(op.c_float(3.1415))
    """
    return _to.MathOp("acos", sth).result

def atan(sth):
    """ Return the arctangent of a number

    :Example:

    >>> op.atan(op.c_float(3.1415))
    """
    return _to.MathOp("atan", sth).result

def max(a1,a2):
    """ Return the maximum of two numbers

    :Example:

    >>> op.max(op.abs(t.Muon[0].p4.Eta()), op.abs(t.Muon[1].p4.Eta()))
    """
    return _to.MathOp("max", a1, a2,
            outType=(_tp.floatType if _tp._hasFloat(a1, a2) else _tp.intType)).result
def min(a1,a2):
    """ Return the minimum of two numbers

    :Example:

    >>> op.min(op.abs(t.Muon[0].p4.Eta()), op.abs(t.Muon[1].p4.Eta()))
    """
    return _to.MathOp("min", a1, a2,
            outType=(_tp.floatType if _tp._hasFloat(a1, a2) else _tp.intType)).result
def in_range(low, arg, up):
    """ Check if a value is inside a range (boundaries excluded)

    :Example:

    >>> op.in_range(10., t.Muon[0].p4.Pt(), 20.)
    """
    return extMethod("rdfhelpers::in_range", returnType=_tp.boolType)(*(_to.adaptArg(iarg, typeHint=_tp.floatType) for iarg in (low, arg, up)))

## Kinematics and helpers
def withMass(arg, massVal):
    """ Construct a Lorentz vector with given mass (taking the other components from the input)

    :Example:

    >>> pW = withMass((j1.p4+j2.p4), 80.4)
    """
    return extMethod("rdfhelpers::withMass", returnType="ROOT::Math::LorentzVector<ROOT::Math::PtEtaPhiM4D<float> >")(arg, _to.adaptArg(massVal, typeHint=_tp.floatType))
def invariant_mass(*args):
    """ Calculate the invariant mass of the arguments

    :Example:

    >>> mElEl = op.invariant_mass(t.Electron[0].p4, t.Electron[1].p4)

    .. note::

        Unlike in the example above, :py:meth:`bamboo.treefunctions.combine` should be used to make N-particle combinations in most practical cases
    """
    if len(args) == 0:
        raise RuntimeError("Need at least one argument to calculate invariant mass")
    elif len(args) == 1:
        return args[0].M()
    elif len(args) == 2:
        return extMethod("ROOT::Math::VectorUtil::InvariantMass", returnType="Float_t")(*args)
    else:
        return sum(*args, outType=args[0]._typeName).M()
def invariant_mass_squared(*args):
    """ Calculate the squared invariant mass of the arguments using ``ROOT::Math::VectorUtil::InvariantMass2``

    :Example:

    >>> m2ElEl = op.invariant_mass2(t.Electron[0].p4, t.Electron[1].p4)
    """
    if len(args) == 0:
        raise RuntimeError("Need at least one argument to calculate invariant mass")
    elif len(args) == 1:
        return args[0].M2()
    elif len(args) == 2:
        return extMethod("ROOT::Math::VectorUtil::InvariantMass2", returnType="Float_t")(*args)
    else:
        return sum(*args, outType=args[0]._typeName).M2()
def deltaPhi(a1, a2):
    """ Calculate the difference in azimutal angles (using ``ROOT::Math::VectorUtil::DeltaPhi``)

    :Example:

    >>> elelDphi = op.deltaPhi(t.Electron[0].p4, t.Electron[1].p4)
    """
    return extMethod("ROOT::Math::VectorUtil::DeltaPhi", returnType="Float_t")(a1, a2)
def Phi_mpi_pi(a):
    """ Return an angle between -pi and pi """
    return extMethod("ROOT::Math::VectorUtil::Phi_mpi_pi", returnType="Float_t")(a)
def Phi_0_2pi(a):
    """ Return an angle between 0 and 2*pi """
    return extMethod("ROOT::Math::VectorUtil::Phi_0_2pi", returnType="Float_t")(a)
def deltaR(a1, a2):
    """ Calculate the Delta R distance (using ``ROOT::Math::VectorUtil::DeltaR``)

    :Example:

    >>> elelDR = op.deltaR(t.Electron[0].p4, t.Electron[1].p4)
    """
    a1 = _to.adaptArg(a1)
    a2 = _to.adaptArg(a2)
    if all(isinstance(arg, _to.Construct) and arg.typeName.startswith("ROOT::Math::LorentzVector<ROOT::Math::PtEtaPhi") for arg in (a1, a2)):
        return sqrt(extMethod("rdfhelpers::deltaR2", returnType="double")(
            a2.args[1].result-a1.args[1].result,
            a2.args[2].result-a1.args[2].result))
    else:
        return extMethod("ROOT::Math::VectorUtil::DeltaR", returnType="Float_t")(a1, a2)

## range operations
def rng_len(sth):
    """ Get the number of elements in a range

    :param rng: input range

    :Example:

    >>> nElectrons = op.rng_len(t.Electron)
    """
    return sth.__len__() ## __builtins__.len checks it is an integer

def rng_sum(rng, fun=lambda x : x, start=c_float(0.)):
    """ Sum the values of a function over a range

    :param rng: input range
    :param fun: function whose value should be used (a callable that takes an element of the range and returns a number)

    :Example:

    >>> totalMuCharge = op.rng_sum(t.Muon, lambda mu : mu.charge)
    """
    return _to.Reduce.fromRngFun(rng, start, ( lambda fn : (
        lambda res, elm : res+fn(elm)
        ) )(fun) )

def rng_count(rng, pred=lambda x : c_bool(True)): ## specialised version of sum, for convenience
    """ Count the number of elements passing a selection

    :param rng: input range
    :param pred: selection predicate (a callable that takes an element of the range and returns a boolean)

    :Example:

    >>> nCentralMu = op.rng_count(t.Muon, lambda mu : op.abs(mu.p4.Eta() < 2.4))
    """
    return _to.Reduce.fromRngFun(rng, c_int(0), ( lambda prd : (
        lambda res, elm : res+switch(prd(elm), c_int(1), c_int(0))
        ) )(pred) )

def rng_product(rng, fun=lambda x : x):
    """ Calculate the production of a function over a range

    :param rng: input range
    :param fun: function whose value should be used (a callable that takes an element of the range and returns a number)

    :Example:

    >>> overallMuChargeSign = op.rng_product(t.Muon, lambda mu : mu.charge)
    """
    return _to.Reduce.fromRngFun(rng, c_float(1.), ( lambda fn : (
        lambda res, elm : res*fn(elm)
        ) )(fun) )

def rng_max(rng, fun=lambda x : x):
    """ Find the highest value of a function in a range

    :param rng: input range
    :param fun: function whose value should be used (a callable that takes an element of the range and returns a number)

    :Example:

    >>> mostForwardMuEta = op.rng_max(t.Muon. lambda mu : op.abs(mu.p4.Eta()))
    """
    return _to.Reduce.fromRngFun(rng, c_float(float("-inf")), ( lambda fn : (
        lambda res, elm : extMethod("std::max", returnType="Float_t")(res, fn(elm))
        ) )(fun) )
def rng_min(rng, fun=lambda x : x):
    """ Find the lowest value of a function in a range

    :param rng: input range
    :param fun: function whose value should be used (a callable that takes an element of the range and returns a number)

    :Example:

    >>> mostCentralMuEta = op.rng_min(t.Muon. lambda mu : op.abs(mu.p4.Eta()))
    """
    return _to.Reduce.fromRngFun(rng, c_float(float("+inf")), ( lambda fn : (
        lambda res, elm : extMethod("std::min", returnType="Float_t")(res, fn(elm))
        ) )(fun) )

def _idxGetter(itemType):
    if itemType is None or itemType == "struct":
        raise RuntimeError(f"Invalid item type: {itemType!s}")
    if ( not isinstance(itemType, str) ) and issubclass(itemType, _tp.ItemProxyBase): ## collection
        return True, (lambda elm : elm.idx)
    else: ## not a collection, so no need to go back to "base" container
        return False, (lambda elm : elm.op.index)

def rng_max_element_index(rng, fun=lambda elm : elm):
    """ Find the index of the element for which the value of a function is maximal

    :param rng: input range
    :param fun: function whose value should be used (a callable that takes an element of the range and returns a number)

    :returns: the index of the maximal element in the base collection if rng is a collection, otherwise (e.g. if rng is a vector or array proxy) the index of the maximal element in rng

    :Example:

    >>> i_mostForwardMu = op.rng_max_element_index(t.Muon. lambda mu : op.abs(mu.p4.Eta()))
    """
    pairType = "std::pair<{0},{1}>".format(_tp.SizeType,_tp.floatType)
    fromColl, getIdx = _idxGetter(rng.valueType)
    return _to.Reduce.fromRngFun(rng,
        construct(pairType, (c_int(-1), c_float(float("-inf")))),
        ( lambda fn,tp,gi : ( lambda ibest, elm : extMethod("rdfhelpers::maxPairBySecond", returnType=tp)(ibest, gi(elm), fn(elm)) ) )(fun, pairType, getIdx)).first

def rng_max_element_by(rng, fun=lambda elm : elm):
    """ Find the element for which the value of a function is maximal

    :param rng: input range
    :param fun: function whose value should be used (a callable that takes an element of the range and returns a number)

    :Example:

    >>> mostForwardMu = op.rng_max_element_by(t.Muon. lambda mu : op.abs(mu.p4.Eta()))
    """
    return rng._getItem(rng_max_element_index(rng, fun=fun))

def rng_min_element_index(rng, fun=lambda elm : elm):
    """ Find the index of the element for which the value of a function is minimal

    :param rng: input range
    :param fun: function whose value should be used (a callable that takes an element of the range and returns a number)

    :returns: the index of the minimal element in the base collection if rng is a collection, otherwise (e.g. if rng is a vector or array proxy) the index of the minimal element in rng

    :Example:

    >>> i_mostCentralMu = op.rng_min_element_index(t.Muon. lambda mu : op.abs(mu.p4.Eta()))
    """
    pairType = "std::pair<{0},{1}>".format(_tp.SizeType,_tp.floatType)
    fromColl, getIdx = _idxGetter(rng.valueType)
    return _to.Reduce.fromRngFun(rng,
        construct(pairType, (c_int(-1), c_float(float("+inf")))),
        ( lambda fn,tp,gi : ( lambda ibest, elm : extMethod("rdfhelpers::minPairBySecond", returnType=tp)(ibest, gi(elm), fn(elm)) ) )(fun, pairType, getIdx)).first

def rng_min_element_by(rng, fun=lambda elm : elm):
    """ Find the element for which the value of a function is minimal

    :param rng: input range
    :param fun: function whose value should be used (a callable that takes an element of the range and returns a number)

    :Example:

    >>> mostCentralMu = op.rng_min_element_by(t.Muon. lambda mu : op.abs(mu.p4.Eta()))
    """
    return rng._getItem(rng_min_element_index(rng, fun=fun))

def rng_mean(rng):
    """ Return the mean of a range

    :param rng: input range

    :Example:

    >>> pdf_mean = op.rng_mean(t.LHEPdfWeight)
    """
    return extMethod("rdfhelpers::Mean", returnType="Double_t")(rng)

def rng_stddev(rng):
    """ Return the (sample) standard deviation of a range

    :param rng: input range

    :Example:

    >>> pdf_uncertainty = op.rng_stddev(t.LHEPdfWeight)
    """
    return extMethod("rdfhelpers::StdDev", returnType="Double_t")(rng)

## early-exit algorithms
def rng_any(rng, pred=lambda elm : elm):
    """ Test if any item in a range passes a selection

    :param rng: input range
    :param pred: selection predicate (a callable that takes an element of the range and returns a boolean)

    :Example:

    >>> hasCentralMu = op.rng_any(t.Muon. lambda mu : op.abs(mu.p4.Eta()) < 2.4)
    """
    _, getIdx = _idxGetter(rng.valueType)
    return  _tp.makeConst(-1, _to.SizeType) != getIdx(_to.Next.fromRngFun(rng, pred))
def rng_find(rng, pred=lambda elm : _tp.makeConst("true", _tp.boolType)):
    """ Find the first item in a range that passes a selection

    :param rng: input range
    :param pred: selection predicate (a callable that takes an element of the range and returns a boolean)

    :Example:

    >>> leadCentralMu = op.rng_find(t.Muon, lambda mu : op.abs(mu.p4.Eta()) < 2.4)
    """
    return _to.Next.fromRngFun(rng, pred)

## range-to-range: selection, combinatorics, systematic variations
def select(rng, pred=(lambda elm : c_bool(True))):
    """ Select elements from the range that pass a cut

    :param rng: input range
    :param pred: selection predicate (a callable that takes an element of the range and returns a boolean)

    :Example:

    >>> centralMuons = op.select(t.Muon, lambda mu : op.abs(mu.p4.Eta()) < 2.4)
    """
    return _to.Select.fromRngFun(rng, pred)

def sort(rng, fun=(lambda elm : c_float(0.))):
    """ Sort the range (ascendingly) by the value of a function applied on each element

    :param rng: input range
    :param fun: function by whose value the elements should be sorted

    :Example:

    >>> muonsByCentrality = op.sort(t.Muon, lambda mu : op.abs(mu.p4.Eta()))
    """
    return _to.Sort.fromRngFun(rng, fun)

def map(rng, fun, valueType=None):
    """ Create a list of derived values for a collection

    This is useful for storing a derived quantity each item of a collection on a skim,
    and also for filling a histogram for each entry in a collection.

    :param rng: input range
    :param fun: function to calculate derived values
    :param valueType: stored return type (optional, ``fun(rng[i])`` should be convertible to this type)

    :Example:

    >>> muon_absEta = op.map(t.Muon, lambda mu : op.abs(mu.p4.Eta()))
    """
    return _to.Map.fromRngFun(rng, fun, typeName=valueType)

def rng_pickRandom(rng, seed=0):
    """ Pick a random element from a range

    :param rng: range to pick an element from
    :param seed: seed for the random generator

    .. caution::

        empty placeholder, to be implemented
    """
    return rng[_to.PseudoRandom(0, rng_len(rng), seed, isIntegral=True)]

def combine(rng, N=None, pred=(lambda *parts : c_bool(True)), samePred=lambda o1,o2: o1.idx < o2.idx):
    """ Create N-particle combination from one or several ranges

    :param rng: range (or iterable of ranges) with basic objects to combine
    :param N: number of objects to combine (at least 2), in case of multiple ranges it does not need to be given (``len(rng)`` will be taken; if specified they should match)
    :param pred: selection to apply to candidates (a callable that takes the constituents and returns a boolean)
    :param samePred: additional selection for objects from the same base container (a callable that takes two objects and returns a boolean, it needs to be true for any sorted pair of objects from the same container in a candidate combination). The default avoids duplicates by keeping the indices (in the base container) sorted; ``None`` will not apply any selection, and consider all combinations, including those with the same object repeated.

    :Example:

    >>> osdimu = op.combine(t.Muon, N=2, pred=lambda mu1,mu2 : mu1.charge != mu2.charge)
    >>> firstosdimu = osdimu[0]
    >>> firstosdimu_Mll = op.invariant_mass(firstosdimu[0].p4, firstosdimu[1].p4)
    >>> oselmu = op.combine((t.Electron, t.Muon), pred=lambda el,mu : el.charge != mu.charge)
    >>> trijet = op.combine(t.Jet, N=3, samePred=lambda j1,j2 : j1.pt > j2.pt)
    >>> trijet = op.combine(t.Jet, N=3, pred=lambda j1,j2,j3 : op.AND(j1.pt > j2.pt, j2.pt > j3.pt), samePred=None)

    .. note::

        The default value for ``samePred`` undoes the sorting that may have been
        applied between the base container(s) and the argument(s) in ``rng``.
        The third and fourth examples above are equivalent, and show how to get
        three-jet combinations, with the jets sorted by decreasing pT.
        The latter is more efficient since it avoids the unnecessary comparison
        ``j1.pt > j3.pt``, which follows from the other two.
        In that case no other sorting should be done, otherwise combinations
        will only be retained if sorted by both criteria; this can be done by
        passing ``samePred=None``.

        ``samePred=(lambda o1,o2 : o1.idx != o2.idx)`` can be used to get all
        permutations.
    """
    if not hasattr(rng, "__iter__"):
        rng = (rng,)
    elif N is None:
        N = len(rng)
    elif N <= 1:
        raise RuntimeError("Can only make combinations of more than one")
    if len(rng) != N and len(rng) != 1:
        raise RuntimeError("If N(={0:d}) input ranges are given, only N-combinations can be made, not {1:d}".format(len(rng), N))
    return _to.Combine.fromRngFun(N, rng, pred, samePred=samePred)

def systematic(nominal, name=None, **kwargs):
    """ Construct an expression that will change under some systematic variations

    This is useful when e.g. changing weights for some systematics. The expressions
    for different variations are assumed (but not checked) to be of the same type, so
    this should only be used for simple types (typically a number or a range of numbers);
    containers etc. need to be taken into account in the decorators.

    :Example:

    >>> psWeight = op.systematic(tree.ps_nominal, name="pdf", up=tree.ps_up, down=tree.ps_down)
    >>> addSys10percent = op.systematic(op.c_float(1.), name="additionalSystematic1", up=op.c_float(1.1), down=op.c_float(0.9))

    :param nominal: nominal expression
    :param name: name of the systematic uncertainty source
    :param kwargs: alternative expressions. "up" and "down" (any capitalization) will be prefixed with name
    """
    if name is None:
        raise ValueError("Systematic must have a name")
    variations = dict()
    for varNm,varExpr in kwargs.items():
        if varNm.upper() == "UP":
            variations["{0}up".format(name)] = _to.adaptArg(varExpr)
        elif varNm.upper() == "DOWN":
            variations["{0}down".format(name)] = _to.adaptArg(varExpr)
        else:
            variations[varNm] = _to.adaptArg(varExpr)
    return _to.SystAltOp(_to.adaptArg(nominal), name, variations).result

class MVAEvaluator:
    """ Small wrapper to make sure MVA evaluation is cached """
    def __init__(self, evaluate):
        self.evaluate = evaluate
    def __call__(self, *inputs):
        return defineOnFirstUse(self.evaluate(initList("std::vector<float>", "float", (static_cast("float", iin) for iin in inputs))))

_mvaExtMap = {
    "TMVA" : [".xml"],
    "Tensorflow" : [".pb"],
    "Torch" : [".pt"],
    "lwtnn" : [".json"]
    }

def mvaEvaluator(fileName, mvaType=None, otherArgs=None, nameHint=None):
    """ Declare and initialize an MVA evaluator

    The C++ object is defined (with :py:meth:`bamboo.treefunctions.define`),
    and can be used as a callable to evaluate.
    The result of any evaluation will be cached automatically.

    Currently the following formats are supported:

    * .xml (``mvaType='TMVA'``) TMVA weights file, evaluated with a ``TMVA::Experimental::RReader``
    * .pt (``mvaType='Torch'``) pytorch script files (loaded with ``torch::jit::load``).
    * .pb (``mvaType='Tensorflow'``) tensorflow graph definition (loaded with Tensorflow-C).
       The ``otherArgs`` keyword argument should be ``(inputNodeNames, outputNodeNames)``, where each
       of the two can be a single string, or an iterable of them.
       In the case of multiple (or multi-dimensional) input nodes,
       the values in the input to the evaluate method should be flattened
       (row-order per node, and then the different nodes).
       The output will be flattened in the same way if there are multiple
       output nodes, or if they have more than one dimension.
    * .json (``mvaType='lwtnn'``) lwtnn json. The ``otherArgs`` keyword argument should be passed
      the lists of input and output nodes/values, as C++ initializer list strings, e.g.
      ``'{ { "node_0", "variable_0" }, { "node_0", "variable_1" } ... }'`` and
      ``'{ "out_0", "out_1" }'``.

    :param fileName: file with MVA weights and structure
    :param mvaType: type of MVA, or library used to evaluate it (Tensorflow, Torch, or lwtnn).
        If absent, this is guessed from the fileName extension
    :param otherArgs: other arguments to construct the MVA evaluator (either as a string (safest), or as an iterable)
    :param nameHint: name hint, see :py:meth:`bamboo.treefunctions.define`

    :returns: a proxy to a method that takes the inputs as arguments, and returns a ``std::vector<float>`` of outputs

    :Example:

    >>> mu = tree.Muon[0]
    >>> nn1 = mvaEvaluator("nn1.pt")
    >>> Plot.make1D("mu_nn1", nn1(mu.pt, mu.eta, mu.phi), hasMu)
    """
    if mvaType == None:
        import os.path
        _,ext = os.path.splitext(fileName)
        try:
            mvaType = next(k for k,v in _mvaExtMap.items() if ext in v)
        except StopIteration:
            raise ValueError("Unknown extension {0!r}, please pass mvaType explicitly".format(ext))
    methodName = "evaluate" ## default, used for wrappers
    isConst = True
    if mvaType == "TMVA":
        cppType = "TMVA::Experimental::RReader"
        argStr = f'"{fileName}"'
        methodName = "Compute"
        isConst = False
    elif mvaType == "Tensorflow":
        from bamboo.root import loadTensorflowC
        loadTensorflowC()
        cppType = "bamboo::TensorflowCEvaluator"
        if isinstance(otherArgs, str):
            otherArgStr = otherArgs
        else:
            inNodeNames, outNodeNames = otherArgs
            otherArgStr = ", ".join(
                f'{{ "{ndNameList}" }}' if isinstance(ndNameList, str)
                else "{{ {0} }}".format(", ".join(f'"{nd}"' for nd in ndNameList))
                for ndNameList in (inNodeNames, outNodeNames))
        argStr = '"{0}", {1}'.format(fileName, otherArgStr)
    elif mvaType == "Torch":
        from bamboo.root import loadLibTorch
        loadLibTorch()
        cppType = "bamboo::TorchEvaluator"
        argStr = f'"{fileName}"'
    elif mvaType == "lwtnn":
        from bamboo.root import loadlwtnn
        loadlwtnn()
        cppType = "bamboo::LwtnnEvaluator"
        argStr = '"{0}", {1}'.format(fileName, (", ".join(repr(arg) for arg in otherArgs) if str(otherArgs) != otherArgs else otherArgs))
    else:
        raise ValueError("Unknown MVA type: {0!r}".format(ext))
    evaluator = define(cppType, '{const}auto <<name>> = {0}({1});'.format(cppType, argStr, const=("const " if isConst else "")), nameHint=nameHint)
    return MVAEvaluator(getattr(evaluator, methodName))
