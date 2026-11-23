"""Build a reviewed, source-pinned description of Lean NDJSON format 3.1.0.

This is a documentation artifact generator, not a proof checker.
"""
from pathlib import Path
import hashlib
import json


HERE = Path(__file__).resolve().parent
EXPORT_COMMIT = "15f6055e299ad5b89345e533cc2192f4cc00f659"
LEAN_COMMIT = "819816b2e0a3bf405af45ae5c7af2491d8f5bee6"


def field(typ, zh):
    return {"type": typ, "meaning_zh": zh}


def record(category, shape, template, *, refs=None, defines=None, notes=None):
    out = {"category": category, "shape": shape, "comment_template_zh": template}
    if refs:
        out["reference_fields"] = refs
    if defines:
        out["defines"] = defines
    if notes:
        out["notes_zh"] = notes
    return out


base_decl = {
    "name": field("NameIdx", "声明名称在名称表中的编号。"),
    "levelParams": field("Array<NameIdx>", "该声明量化的宇宙参数名称；数组顺序有意义。这里是名称引用，不是层级表引用。"),
    "type": field("ExprIdx", "声明的类型表达式编号。"),
}
base_refs = {"name": "NameIdx", "levelParams[*]": "NameIdx", "type": "ExprIdx"}
all_decl = field("Array<NameIdx>", "同一个 mutual 块中的全部声明名称，含自身；不是全部依赖声明。")
unsafe = field("Bool", "是否带有 unsafe 标记；该字段值本身不是对文件完成验证的证据。")
records = {}
records["meta"] = record("metadata", {"meta": {
    "exporter": {"name": field("String", "导出器名称。"), "version": field("String", "导出器在文件中写入的自描述版本。")},
    "lean": {"version": field("String", "文件自报的 Lean 版本。"), "githash": field("String", "文件自报的 Lean 源码提交。")},
    "format": {"version": field("String", "NDJSON 序列化格式版本。")},
}}, "文件元信息：导出器={meta.exporter.name}，自报导出版本={meta.exporter.version}；格式={meta.format.version}；Lean={meta.lean.version}，提交={meta.lean.githash}。这是来源描述，不是本次运行的证明检查结果。")

records["str"] = record("name", {"str": {
    "pre": field("NameIdx", "父名称/前缀名称引用。"), "str": field("String", "追加的字符串名称分量。")},
    "in": field("NameIdxDef", "本行新定义的名称编号。")},
    "定义名称 Name#{in}：在前缀 Name#{str.pre} 后追加字符串分量 {str.str}。",
    refs={"str.pre": "NameIdx"}, defines={"in": "NameIdx"})
records["num"] = record("name", {"num": {
    "pre": field("NameIdx", "父名称/前缀名称引用。"), "i": field("Nat", "追加的自然数名称分量；不是名称表编号。")},
    "in": field("NameIdxDef", "本行新定义的名称编号。")},
    "定义名称 Name#{in}：在前缀 Name#{num.pre} 后追加数值分量 {num.i}。",
    refs={"num.pre": "NameIdx"}, defines={"in": "NameIdx"})
records["succ"] = record("level", {"succ": field("LevelIdx", "被加一的宇宙层级引用。"), "il": field("LevelIdxDef", "本行新定义的层级编号。")},
    "定义层级 Level#{il} = succ(Level#{succ})，即该宇宙层级加一。", refs={"succ":"LevelIdx"}, defines={"il":"LevelIdx"})
records["max"] = record("level", {"max": field("Tuple<LevelIdx,LevelIdx>", "恰好两个层级引用；取二者的最大层级。"), "il": field("LevelIdxDef", "本行新定义的层级编号。")},
    "定义层级 Level#{il} = max(Level#{max[0]}, Level#{max[1]})。", refs={"max[0]":"LevelIdx","max[1]":"LevelIdx"}, defines={"il":"LevelIdx"})
records["imax"] = record("level", {"imax": field("Tuple<LevelIdx,LevelIdx>", "恰好两个层级引用；当第二项取值为0时结果为0，否则取最大值。"), "il": field("LevelIdxDef", "本行新定义的层级编号。")},
    "定义层级 Level#{il} = imax(Level#{imax[0]}, Level#{imax[1]})：第二项为0时结果为0，否则为最大值。", refs={"imax[0]":"LevelIdx","imax[1]":"LevelIdx"}, defines={"il":"LevelIdx"})
records["param"] = record("level", {"param": field("NameIdx", "宇宙参数的名称引用。"), "il": field("LevelIdxDef", "本行新定义的层级编号。")},
    "定义层级 Level#{il}：以名称 Name#{param} 表示的宇宙参数。", refs={"param":"NameIdx"}, defines={"il":"LevelIdx"})


def expr_record(tag, payload, template, refs=None, notes=None):
    records[tag] = record("expression", {tag: payload, "ie": field("ExprIdxDef", "本行新定义的表达式编号。")}, template,
        refs=refs, defines={"ie":"ExprIdx"}, notes=notes)


expr_record("bvar", field("Nat", "de Bruijn 绑定距离，0指当前使用处最内层绑定变量；不是任意全局表的编号。"),
    "定义表达式 Expr#{ie}：绑定变量 bvar {bvar}，在使用它的表达式中向外数第 {bvar}+1 个绑定层。", notes=[
        "无法仅凭本行确定变量的名称、类型或作用域是否有效。相同 bvar 节点可在不同绑定上下文中共享。",
        "绑定变量的作用域由表达式 DAG 的使用路径决定，不是 NDJSON 的前后行位置。"])
expr_record("sort", field("LevelIdx", "Sort 的宇宙层级引用；Level#0表示0。"),
    "定义表达式 Expr#{ie} = Sort(Level#{sort})。", refs={"sort":"LevelIdx"}, notes=["当层级为0时该Sort为Prop；仅凭编号非零不能断言层级求值非零。"])
expr_record("const", {"name": field("NameIdx", "所引用常量的名称。"), "us": field("Array<LevelIdx>", "依序实例化该常量宇宙参数的层级引用。")},
    "定义表达式 Expr#{ie}：引用常量 Name#{const.name}，宇宙实参为 {const.us}（层级表编号）。", refs={"const.name":"NameIdx","const.us[*]":"LevelIdx"}, notes=[
        "这里的name需要先出现在名称表；并不要求这个名称对应的声明行已经输出。归纳组内可以先引用其名称。",
        "常量也可以指类型、构造器、递归原理、定义或公理，不能一概称为定理。"])
expr_record("app", {"fn": field("ExprIdx", "函数位置的表达式引用。"), "arg": field("ExprIdx", "实参位置的表达式引用。")},
    "定义表达式 Expr#{ie}：将函数位置 Expr#{app.fn} 应用于参数 Expr#{app.arg}。", refs={"app.fn":"ExprIdx","app.arg":"ExprIdx"})
for tag, what in (("lam","lambda函数/抽象项"),("forallE","依赖函数类型（Pi类型；命题情形下表示全称量化）")):
    expr_record(tag, {
        "name":field("NameIdx","绑定变量的显示名称引用；实际绑定由de Bruijn索引表示。"),
        "type":field("ExprIdx","绑定变量的类型；新变量不在该类型的自身作用域内。"),
        "body":field("ExprIdx","主体；进入主体时增加一层绑定。"),
        "binderInfo":field("BinderInfo","显式/隐式/严格隐式/实例隐式参数方式。")},
        f"定义表达式 Expr#{{ie}}：{what}；变量名 Name#{{{tag}.name}}，类型 Expr#{{{tag}.type}}，主体 Expr#{{{tag}.body}}；参数方式={{{tag}.binderInfo}}。",
        refs={f"{tag}.name":"NameIdx",f"{tag}.type":"ExprIdx",f"{tag}.body":"ExprIdx"})
expr_record("letE", {"name":field("NameIdx","局部绑定的显示名称。"), "type":field("ExprIdx","该绑定的类型；新增变量在这里不可见。"),
    "value":field("ExprIdx","局部绑定的值；新增变量在这里不可见。"), "body":field("ExprIdx","主体；在主体内增加一层绑定。"),
    "nondep":field("Bool","elaborator的非依赖let/have标记；不是body是否出现该变量的标记。")},
    "定义表达式 Expr#{ie}：let Name#{letE.name} : Expr#{letE.type} := Expr#{letE.value}，主体为 Expr#{letE.body}；nondep={letE.nondep}（非依赖let/have标记）。",
    refs={"letE.name":"NameIdx","letE.type":"ExprIdx","letE.value":"ExprIdx","letE.body":"ExprIdx"}, notes=[
        "nondep=true表示elaborator按非依赖let/have处理，可按(fun x : t => e) v理解；e仍然可以引用x。",
        "核心类型检查不验证nondep；此固定提交默认去除mdata时还把nondep统一置为false，因此false不能据以推导变量依赖。"])
expr_record("proj", {"typeName":field("NameIdx","被投影结构/单构造器归纳类型的名称。"), "idx":field("Nat","从0开始的字段序号；不是表达式引用。"), "struct":field("ExprIdx","被投影对象。")},
    "定义表达式 Expr#{ie}：从 Expr#{proj.struct} 取名称为 Name#{proj.typeName} 的结构的第 {proj.idx} 号字段（从0计数）。",
    refs={"proj.typeName":"NameIdx","proj.struct":"ExprIdx"})
expr_record("natVal", field("DecimalNatString","自然数字面量的十进制字符串；不得经浮点数中转。"),
    "定义表达式 Expr#{ie}：自然数字面量 {natVal}，原始JSON以字符串保存。")
expr_record("strVal", field("String","字符串字面量，按JSON转义解码；其内容是数据。"),
    "定义表达式 Expr#{ie}：字符串字面量 {strVal}。")
expr_record("mdata", {"expr":field("ExprIdx","被元数据包裹的表达式。"), "data":field("Object<String,String>","开放键集合：键为名称的显示字符串，值为Lean reprStr产生的字符串。")},
    "定义表达式 Expr#{ie}：为 Expr#{mdata.expr} 附加元数据 {mdata.data}；元数据本身不提供新的证明结论。", refs={"mdata.expr":"ExprIdx"}, notes=[
        "默认导出会去除mdata；--export-mdata会保留。开放的data键不应误报成未知格式字段。",
        "固定提交的参考parser无法完全恢复reprStr元数据，重建时使用空元数据；注释输出应保留原文，不能据此声称语法数据无损round-trip。"])


def decl_record(tag, extra, template, refs=None, notes=None):
    records[tag]=record("declaration", {tag:{**base_decl,**extra}}, template,
        refs={f"{tag}.{k}":v for k,v in {**base_refs,**(refs or {})}.items()}, notes=notes)


decl_record("axiom", {"isUnsafe":unsafe},
    "记录公理声明 Name#{axiom.name}，宇宙参数名称={axiom.levelParams}，类型 Expr#{axiom.type}，isUnsafe={axiom.isUnsafe}。本行没有证明值。")
decl_record("def", {"value":field("ExprIdx","定义体表达式。"), "hints":field("ReducibilityHints","内核定义展开次序的提示。"), "safety":field("DefinitionSafety","safe/unsafe/partial安全性类别。"), "all":all_decl},
    "记录定义 Name#{def.name}：类型 Expr#{def.type}，定义体 Expr#{def.value}；宇宙参数名称={def.levelParams}，展开提示={def.hints}，safety={def.safety}，同mutual块名称={def.all}。",
    refs={"value":"ExprIdx","all[*]":"NameIdx"}, notes=["hints中的opaque仅为展开次序提示，不等同顶层opaque声明，也不是禁止内核展开。"])
decl_record("opaque", {"value":field("ExprIdx","opaque声明的值；与无证明值的公理不同。"),"all":all_decl,"isUnsafe":unsafe},
    "记录opaque声明 Name#{opaque.name}：类型 Expr#{opaque.type}，值 Expr#{opaque.value}；宇宙参数名称={opaque.levelParams}，同mutual块名称={opaque.all}，isUnsafe={opaque.isUnsafe}。",
    refs={"value":"ExprIdx","all[*]":"NameIdx"})
decl_record("thm", {"value":field("ExprIdx","此定理声明所提供的证明项表达式。"),"all":all_decl},
    "记录定理声明 Name#{thm.name}：待对应的命题类型 Expr#{thm.type}，提供的证明项 Expr#{thm.value}；宇宙参数名称={thm.levelParams}，同mutual块名称={thm.all}。本注释未独立执行内核验证。",
    refs={"value":"ExprIdx","all[*]":"NameIdx"})
decl_record("quot", {"kind":field("QuotKind","商类型内核常量类别：type/ctor/lift/ind。")},
    "记录商类型原语 Name#{quot.name}：kind={quot.kind}，类型 Expr#{quot.type}，宇宙参数名称={quot.levelParams}。")
records["inductive"]=record("declaration",{"inductive":{
    "types":field("Array<InductiveVal>","本组归纳类型及相关辅助类型的完整条目。"),
    "ctors":field("Array<ConstructorVal>","本组构造器的完整条目。"),
    "recs":field("Array<RecursorVal>","本组递归/归纳原理的完整条目。")}},
    "记录一个归纳/相互归纳声明组：types={逐条解释全部InductiveVal}；ctors={逐条解释全部ConstructorVal}；recs={逐条解释全部RecursorVal及其rules}。",
    notes=["构造器与递归原理为同一inductive行里的嵌套条目，不是独立顶层记录类型。","官方内核会从归纳声明推导recursor及若干描述字段；导出包含这些派生数据以便分析工具使用。"])

structures={
    "InductiveVal":{
        "shape":{**base_decl,
            "numParams":field("Nat","固定在各构造器间的参数数量。"),
            "numIndices":field("Nat","可随构造器变化的类型索引数量。"),
            "all":field("Array<NameIdx>","同相互归纳声明中的全部归纳类型名称，含自身。"),
            "ctors":field("Array<NameIdx>","该归纳类型的构造器名称。"),
            "numNested":field("Nat","嵌套归纳出现所生成的辅助数据类型数量。"),
            "isRec":field("Bool","是否递归：该归纳类型是否出现在构造器参数中。"),
            "isReflexive":field("Bool","至少一个构造器是否接受返回所定义类型的函数作为参数；这里不是关系的自反性。"),
            "isUnsafe":unsafe},
        "reference_fields":{**base_refs,"all[*]":"NameIdx","ctors[*]":"NameIdx"},
        "comment_template_zh":"归纳类型 Name#{name}：type=Expr#{type}，levelParams={levelParams}，固定参数数numParams={numParams}，变化索引数numIndices={numIndices}，同组类型all={all}，构造器ctors={ctors}，嵌套辅助类型数numNested={numNested}，递归标记isRec={isRec}，函数返回本类型标记isReflexive={isReflexive}，isUnsafe={isUnsafe}。",
    },
    "ConstructorVal":{
        "shape":{**base_decl,
            "induct":field("NameIdx","所属归纳类型名称。"),
            "cidx":field("Nat","在所属归纳类型构造器列表中的位置编号，从0计数。"),
            "numParams":field("Nat","该归纳类型的参数数量。"),
            "numFields":field("Nat","构造器字段数量，不含归纳类型参数。"),
            "isUnsafe":unsafe},
        "reference_fields":{**base_refs,"induct":"NameIdx"},
        "comment_template_zh":"构造器 Name#{name}：type=Expr#{type}，levelParams={levelParams}，所属类型induct=Name#{induct}，位置cidx={cidx}，参数数numParams={numParams}，字段数numFields={numFields}，isUnsafe={isUnsafe}。",
    },
    "RecursorVal":{
        "shape":{**base_decl,
            "all":field("Array<NameIdx>","生成该递归原理的相互归纳声明中全部归纳类型名称。"),
            "numParams":field("Nat","参数数量。"),
            "numIndices":field("Nat","索引数量。"),
            "numMotives":field("Nat","递归/归纳目标族motive的数量。"),
            "numMinors":field("Nat","对应构造器分支的次要前提数量。"),
            "rules":field("Array<RecursorRule>","各构造器对应的iota归约规则。"),
            "k":field("Bool","是否支持K-like归约；不是本行新增的公理K声明。"),
            "isUnsafe":unsafe},
        "reference_fields":{**base_refs,"all[*]":"NameIdx","rules[*].ctor":"NameIdx","rules[*].rhs":"ExprIdx"},
        "comment_template_zh":"递归/归纳原理 Name#{name}：type=Expr#{type}，levelParams={levelParams}，同组类型all={all}，参数数numParams={numParams}，索引数numIndices={numIndices}，目标族数numMotives={numMotives}，次要前提数numMinors={numMinors}，rules={逐条解释所有RecursorRule}，K-like归约标记k={k}，isUnsafe={isUnsafe}。",
    },
    "RecursorRule":{
        "shape":{"ctor":field("NameIdx","触发此归约规则的构造器名称。"), "nfields":field("Nat","该构造器字段数，不计归纳类型参数。"), "rhs":field("ExprIdx","归约规则右侧表达式。")},
        "reference_fields":{"ctor":"NameIdx","rhs":"ExprIdx"},
        "comment_template_zh":"构造器ctor=Name#{ctor}的归约规则：字段数nfields={nfields}，右侧rhs=Expr#{rhs}。",
    },
}

source_paths=["format_ndjson.md","Export.lean","Export/Parse.lean","README.md","lean-toolchain"]
sources=[]
for p in source_paths:
    data=(HERE/p).read_bytes()
    sources.append({"id":p,"repository":"leanprover/lean4export","commit":EXPORT_COMMIT,"path":p,
        "url":f"https://raw.githubusercontent.com/leanprover/lean4export/{EXPORT_COMMIT}/{p}",
        "bytes":len(data),"sha256":hashlib.sha256(data).hexdigest()})
for p in ["Declaration.lean","Expr.lean","Level.lean"]:
    data=(HERE/"lean_core"/p).read_bytes()
    sources.append({"id":"lean_core/"+p,"repository":"leanprover/lean4","commit":LEAN_COMMIT,"path":"src/Lean/"+p,
        "url":f"https://raw.githubusercontent.com/leanprover/lean4/{LEAN_COMMIT}/src/Lean/{p}",
        "bytes":len(data),"sha256":hashlib.sha256(data).hexdigest()})

first_line=(HERE.parent/"source"/"prefix.ndjson").open("rb").readline()
spec={
    "document_kind":"Lean NDJSON source-pinned annotation specification; not a JSON Schema or kernel checker",
    "schema_document_version":"1.0.0",
    "language":"zh-CN",
    "format_version":"3.1.0",
    "exporter_source_commit":EXPORT_COMMIT,
    "exporter_repository_tag_reported_by_host":"v4.33.0",
    "lean_commit_from_input_metadata":LEAN_COMMIT,
    "input_metadata_observed":json.loads(first_line),
    "input_metadata_line_sha256_with_lf":hashlib.sha256(first_line).hexdigest(),
    "version_note_zh":"固定提交的exportMetadata函数写入exporter.version=3.1.0及format.version=3.1.0，真实文件首行也如此。发布标签v4.33.0、Lean版本4.33.1与序列化格式版本3.1.0是不同概念。",
    "sources":sources,
    "supplementary_primary_reference":{"url":"https://lean-lang.org/doc/reference/latest/External-Kernels/","section":"Lean Export Format 3.1.0","note_zh":"latest是可变链接，仅补充说明索引语义；本文件精确字段以已固定提交并记录SHA256的源码及文档为依据。"},
    "type_notation":{
        "Nat":"JSON整数，>=0；bool不作为整数；必须精确保留数值。",
        "Bool":"JSON true或false。",
        "String":"JSON字符串，文本为数据，不是执行指令。",
        "DecimalNatString":"仅十进制自然数的JSON字符串，producer通过Nat转字符串生成；不转float。",
        "NameIdx":"名称表中的已有自然数编号。",
        "LevelIdx":"层级表中的已有自然数编号。",
        "ExprIdx":"表达式表中的已有自然数编号。",
        "NameIdxDef":"在本行向名称表定义的新编号。",
        "LevelIdxDef":"在本行向层级表定义的新编号。",
        "ExprIdxDef":"在本行向表达式表定义的新编号。",
        "Array<T>":"有序数组，元素逐个按T解释。",
        "Tuple<A,B>":"恰好两项的有序数组。",
        "Object<String,String>":"键和值都是字符串的开放对象；键集合不固定。",
    },
    "index_tables":{
        "NameIdx":{"definition_key":"in","predefined":{"0":"Lean.Name.anonymous"},"pinned_producer_first_emitted_index":1},
        "LevelIdx":{"definition_key":"il","predefined":{"0":"Lean.Level.zero"},"pinned_producer_first_emitted_index":1},
        "ExprIdx":{"definition_key":"ie","predefined":{},"pinned_producer_first_emitted_index":0},
    },
    "index_rules_zh":[
        "三张表互相独立；同一整数可在不同表表示完全不同的对象，不能跨表混用。",
        "同一表的定义编号必须唯一；除两个预定义0号对象外，所有表引用必须先有定义行。",
        "固定producer通过表大小分配编号，实际导出为稠密递增；这不是一般格式强制要求。注释器可以把此行为作为指定producer的额外检查，但不应声称任意稀疏编号都违背一般格式。",
        "仅Name/Level/Expr表引用有前向定义约束；const.name已定义为名称，不表示同名声明行必须已输出。",
        "bvar、num.i、proj.idx、hints.regular、cidx、numParams/numIndices/numNested/numFields/numMotives/numMinors/nfields是数值，不是表引用。",
        "levelParams是NameIdx数组；const.us是LevelIdx数组。",
        "编号本身不是原始行号、证明步骤号或内存地址。",
        "名称显示成点分形式仅方便阅读，字符串分量本身可能含特殊字符；原分量与NameIdx必须保留，不能假装显示串一定是可复制的Lean源码。",
    ],
    "record_variants":records,
    "nested_structures":structures,
    "enums":{
        "BinderInfo":{
            "default":"显式参数，例如(x : A)。",
            "implicit":"隐式参数，例如{x : A}。",
            "strictImplicit":"严格隐式参数，例如⦃x : A⦄。",
            "instImplicit":"实例隐式参数，例如[Decidable P]。",
        },
        "ReducibilityHints":{
            "opaque":"展开次序提示opaque；与另一种hint比较时优先展开另一方，并不禁止内核展开本定义。",
            "abbrev":"展开次序提示abbrev，通常优先于regular与opaque展开。",
            "{regular: Nat}":"带UInt32定义高度的regular提示；比较regular定义时优先展开较高者。值是高度，不是引用。producer值范围为0至4294967295。",
        },
        "DefinitionSafety":{
            "safe":"Lean声明安全性枚举safe。该标签不表示本注释器已验证证明。",
            "unsafe":"Lean声明安全性枚举unsafe；应显式保留并报告。",
            "partial":"Lean声明安全性枚举partial；不得翻译成“部分完成的数学证明”。",
        },
        "QuotKind":{"type":"Quot商类型原语。","ctor":"Quot.mk商类型构造器原语。","lift":"Quot.lift商类型提升原语。","ind":"Quot.ind商类型归纳原语。"},
    },
    "binder_scope_zh":[
        "lam和forallE的type仍在外层上下文，body增加一层绑定。",
        "letE的type与value仍在外层上下文，body增加一层绑定。",
        "bvar 0是使用处最内层绑定，bvar 1是再外一层；相同共享节点可在不同使用处对应不同变量名。",
        "仅逐行语法注释无法证明全部绑定作用域有效；需要从根类型/证明项遍历作用域或运行内核。",
    ],
    "pinned_exporter_behavior_zh":[
        "exportMData默认false；默认移除mdata且统一letE.nondep=false。",
        "exportUnsafe默认false；可由--export-unsafe开启。文件元信息未记录该CLI选项，不能只据默认值声称输入中不存在unsafe。",
        "free variable、expression metavariable与level metavariable不属于有效导出变体。",
        "inductive一行包含整组types/ctors/recs，普通递归原理条目仅在其中出现。",
        "参考Parse.lean的parseFile直接读过首行而未验证元信息；其成功运行本身不等于完整格式或证明验证。",
        "参考parser可为旧输入缺失的opaque.isUnsafe取false；但此固定producer始终输出该字段。注释原文件时不得静默补字段或更改原行。",
        "参考parser的addName/addLevel/addExpr直接insert；注释审计仍应按格式规范报告重复定义，不可将parser行为误当允许重复索引的规范。",
    ],
    "coverage_and_unknown_policy_zh":[
        "每条原始物理行保留其原始UTF-8字节及原行号；注释与该行一一对应。不得重新排序或把JSON重序列化后冒充原文。",
        "已知记录须解释本variant全部字段；含嵌套数组时解释全部条目及规则，而不只写一个笼统总数。",
        "遇到未知顶层variant、未知受约束字段、未知枚举、字段缺失或类型不符时，保留原行，标为“未知/格式异常，未作语义解释”，记录原行号与完整字段/值并计数。不能猜测或忽略。",
        "允许工具继续保留其他可解析行，但只要存在未解释记录，就不得宣称全文件语义注释完全覆盖；应在交付报告明确未解释数量。",
        "mdata.data为开放键对象；其中任意键值不是新的记录variant，不应按固定字段表误报。",
        "去除注释后须能逐字节重建原始输入；如交付只是前缀/样本必须显式标注行号范围，不能标成全文件。",
        "NDJSON不支持//注释。带//注释的阅读版必须用.txt或.jsonl-with-comments等明确说明的扩展名；不得直接交给期待纯NDJSON的内核。",
        "语法解析、编号检查、逐行覆盖及哈希一致性均不是Lean内核的类型/证明检查。",
        "表达式记录通常是共享语法树节点，不可一行一行编造数学推理步骤；定理记录只表示文件声明了type及value。",
    ],
}
(HERE/"format_spec.json").write_text(json.dumps(spec,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
(HERE/"source_hashes.json").write_text(json.dumps(sources,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
print(HERE/"format_spec.json")
print("record variants:",len(records),"nested structures:",len(structures))
