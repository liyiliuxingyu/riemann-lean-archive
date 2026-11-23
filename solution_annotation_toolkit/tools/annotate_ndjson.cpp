#include "vendor/simdjson.h"
#include <openssl/evp.h>
#include <zstd.h>
#include <algorithm>
#include <array>
#include <charconv>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <map>
#include <stdexcept>
#include <string>
#include <string_view>
#include <unordered_map>
#include <vector>
#include <fcntl.h>
#include <sys/mman.h>
#include <unistd.h>

namespace fs=std::filesystem;
using E=simdjson::dom::element;
using O=simdjson::dom::object;
using A=simdjson::dom::array;
using U=uint64_t;
using Clock=std::chrono::steady_clock;

std::string dec(U n){char b[32];auto q=std::to_chars(b,b+sizeof b,n);return {b,q.ptr};}
void num(std::string &s,U n){char b[32];auto q=std::to_chars(b,b+sizeof b,n);s.append(b,q.ptr);}
std::string quote(std::string_view v){
 std::string s; s.reserve(v.size()+2);s+='"';
 const char hex[]="0123456789abcdef";
 for(size_t i=0;i<v.size();i++){
  unsigned char c=v[i];
  if(c=='"'||c=='\\'){s+='\\';s+=c;}
  else if(c<32||c==127){s+="\\u00";s+=hex[c>>4];s+=hex[c&15];}
  else if(c==0xc2&&i+1<v.size()&&(unsigned char)v[i+1]>=0x80&&(unsigned char)v[i+1]<=0x9f){unsigned char d=v[++i];s+="\\u00";s+=hex[d>>4];s+=hex[d&15];}
  else if(c==0xe2&&i+2<v.size()&&(unsigned char)v[i+1]==0x80&&((unsigned char)v[i+2]==0xa8||(unsigned char)v[i+2]==0xa9)){s+=(unsigned char)v[i+2]==0xa8?"\\u2028":"\\u2029";i+=2;}
  else s+=c;
 }
 s+='"';return s;
}
std::string preview(std::string_view s,size_t n=180){
 if(s.size()<=n)return quote(s);
 while(n && (static_cast<unsigned char>(s[n])&0xc0)==0x80)--n;
 return quote(s.substr(0,n))+"…（完整UTF-8值共"+dec(s.size())+"字节，原文保留）";
}
U u(E e){return e.get_uint64().value();}
std::string_view sv(E e){return e.get_string().value();}
bool bo(E e){return e.get_bool().value();}
std::string tf(E e){return bo(e)?"true":"false";}
void keys(E e,std::initializer_list<std::string_view> expected){
 O o=e.get_object().value(); if(o.size()!=expected.size())throw std::runtime_error("Unexpected field count");
 for(auto f:o){bool ok=false;for(auto k:expected)if(f.key==k){ok=true;break;}if(!ok)throw std::runtime_error("Unknown field: "+std::string(f.key));}
}

class Hash{
 EVP_MD_CTX *p=EVP_MD_CTX_new(); bool ended=false;
 public:
 Hash(){if(!p||EVP_DigestInit_ex(p,EVP_sha256(),nullptr)!=1)throw std::runtime_error("SHA initialization failed");}
 ~Hash(){EVP_MD_CTX_free(p);}
 void add(const void *b,size_t n){if(n && EVP_DigestUpdate(p,b,n)!=1)throw std::runtime_error("SHA update failed");}
 std::string finish(){if(ended)throw std::runtime_error("SHA already finalized");ended=true;unsigned char b[EVP_MAX_MD_SIZE];unsigned int n=0;if(EVP_DigestFinal_ex(p,b,&n)!=1)throw std::runtime_error("SHA finalization failed");std::string s;const char x[]="0123456789abcdef";for(unsigned i=0;i<n;i++){s+=x[b[i]>>4];s+=x[b[i]&15];}return s;}
};

// File-backed name components avoid retaining the giant expression DAG or
// every expanded qualified name in RAM. The OS may evict clean mapped pages.
class MappedFile{
 int fd=-1; char *ptr=nullptr; size_t cap=0,used=0;
 public:
 explicit MappedFile(const fs::path &p){fd=::open(p.c_str(),O_RDWR|O_CREAT|O_EXCL,0600);if(fd<0)throw std::runtime_error("Cannot create name store: "+p.string());}
 ~MappedFile(){if(ptr)munmap(ptr,cap);if(fd>=0){ftruncate(fd,used);close(fd);}}
 void ensure(size_t n){if(n<=cap)return;size_t next=((n+(64ull<<20)-1)/(64ull<<20))*(64ull<<20);if(ptr)munmap(ptr,cap);if(ftruncate(fd,next))throw std::runtime_error("Name store resize failed");ptr=(char*)mmap(nullptr,next,PROT_READ|PROT_WRITE,MAP_SHARED,fd,0);if(ptr==MAP_FAILED){ptr=nullptr;throw std::runtime_error("Name store mmap failed");}cap=next;}
 size_t append(const void *data,size_t n){size_t at=used;ensure(used+n);if(n)memcpy(ptr+used,data,n);used+=n;return at;}
 const char *at(size_t offset)const{if(offset>used)throw std::runtime_error("Name offset out of range");return ptr+offset;}
 size_t size()const{return used;}
};
struct NameNode{U parent;U data;uint32_t length;uint8_t numeric;uint8_t pad[3];};
class Names{
 MappedFile idx,blob;U count=0;
 std::unordered_map<U,std::string> cache;
 public:
 explicit Names(const fs::path &dir):idx(dir/"names.idx"),blob(dir/"names.utf8") {NameNode a{};idx.append(&a,sizeof a);count=1;cache.emplace(0,"〈匿名〉");}
 void str(U id,U parent,std::string_view s){if(id!=count||parent>=count)throw std::runtime_error("Nonsequential or forward Name index");if(s.size()>UINT32_MAX)throw std::runtime_error("Name component too long");NameNode n{};n.parent=parent;n.data=blob.append(s.data(),s.size());n.length=s.size();idx.append(&n,sizeof n);count++;}
 void numeric(U id,U parent,U val){if(id!=count||parent>=count)throw std::runtime_error("Nonsequential or forward Name index");NameNode n{};n.parent=parent;n.data=val;n.numeric=1;idx.append(&n,sizeof n);count++;}
 std::string render(U id){if(id==0)return "〈匿名〉";if(id>=count)throw std::runtime_error("Invalid Name reference");if(auto it=cache.find(id);it!=cache.end())return it->second;
  std::vector<std::string> parts;U x=id;
  while(x){NameNode n;memcpy(&n,idx.at(x*sizeof(NameNode)),sizeof n);std::string c;
   if(n.numeric)c="#"+dec(n.data);else{std::string_view t(blob.at(n.data),n.length);bool escape=t.empty();for(unsigned char b:t)if(b=='.'||b=='#'||b=='"'||b=='\\'||b<33)escape=true;c=escape?quote(t):std::string(t);}parts.push_back(std::move(c));x=n.parent;
  }
  std::string out;for(auto it=parts.rbegin();it!=parts.rend();++it){if(!out.empty())out+='.';out+=*it;}
  if(cache.size()>65536)cache.clear();cache.emplace(id,out);return out;
 }
 U size()const{return count;}size_t disk_bytes()const{return idx.size()+blob.size();}
};

class Explainer{
 Names names; U nextL=1,nextE=0;std::string s;
 void N(U id){if(id>=names.size())throw std::runtime_error("Forward/invalid Name reference N"+dec(id));s+='N';num(s,id);}
 void L(U id){if(id>=nextL)throw std::runtime_error("Forward/invalid Level reference L"+dec(id));s+='L';num(s,id);}
 void X(U id){if(id>=nextE)throw std::runtime_error("Forward/invalid Expr reference E"+dec(id));s+='E';num(s,id);}
 void name(E e,bool resolved=false){U id=u(e);N(id);if(resolved){s+='(';s+=quote(names.render(id));s+=')';}}
 void ref(E e,char which){if(which=='N')name(e);else if(which=='L')L(u(e));else X(u(e));}
 void arr(E e,char which){s+='[';bool first=true;A values=e.get_array().value();for(E a:values){if(!first)s+=',';first=false;ref(a,which);}s+=']';}
 void idprefix(char k,U id){s+=k;num(s,id);s+="：";}
 void binder(E e){auto v=sv(e);if(v=="default")s+="显式参数(default)";else if(v=="implicit")s+="隐式参数(implicit)";else if(v=="strictImplicit")s+="严格隐式参数(strictImplicit)";else if(v=="instImplicit")s+="实例隐式参数(instImplicit)";else throw std::runtime_error("Unknown binderInfo");}
 void common(E p){s+="名称=";name(p["name"],true);s+="；宇宙参数名称=";arr(p["levelParams"],'N');s+="；类型=";X(u(p["type"]));}
 void fieldNat(E p,const char *key,const char *zh){s+="；";s+=zh;s+='=';num(s,u(p[key]));}
 void fieldBool(E p,const char *key,const char *zh){s+="；";s+=zh;s+='=';s+=tf(p[key]);}
 void group(E p){s+="；同组名称all=";arr(p["all"],'N');}
 public:
 std::map<std::string,U> counts; U lines=0;
 explicit Explainer(const fs::path &dir):names(dir){s.reserve(4096);}
 U name_count()const{return names.size()-1;}U level_count()const{return nextL-1;}U expr_count()const{return nextE;}size_t name_bytes()const{return names.disk_bytes();}
 const std::string &explain(E doc,U line){
  s.clear();s+="-- @line ";num(s,line);s+=' ';
  std::string_view kind;E p;U id=0;char table=0;unsigned prim=0,idfields=0;
  O root=doc.get_object().value();for(auto f:root){
   if(f.key=="in"||f.key=="il"||f.key=="ie"){id=u(f.value);table=f.key=="in"?'N':f.key=="il"?'L':'E';idfields++;}
   else{kind=f.key;p=f.value;prim++;}
  }
  if(line==1&&kind!="meta")throw std::runtime_error("First record must be metadata");
  if(prim!=1||idfields>1)throw std::runtime_error("Invalid top-level record shape");
  bool isName=(kind=="str"||kind=="num"),isLevel=(kind=="succ"||kind=="max"||kind=="imax"||kind=="param");
  bool isExpr=(kind=="bvar"||kind=="sort"||kind=="const"||kind=="app"||kind=="lam"||kind=="forallE"||kind=="letE"||kind=="proj"||kind=="natVal"||kind=="strVal"||kind=="mdata");
  char expect=isName?'N':isLevel?'L':isExpr?'E':0;
  if(table!=expect || (expect && idfields!=1))throw std::runtime_error("Wrong index table for "+std::string(kind));
  if(table=='L'&&id!=nextL)throw std::runtime_error("Level indices are not sequential");
  if(table=='E'&&id!=nextE)throw std::runtime_error("Expr indices are not sequential");
  if(kind=="meta"){
   if(line!=1)throw std::runtime_error("Metadata not first");keys(p,{"exporter","lean","format"});keys(p["exporter"],{"name","version"});keys(p["lean"],{"githash","version"});keys(p["format"],{"version"});
   if(sv(p["format"]["version"])!="3.1.0")throw std::runtime_error("Unsupported export format");
   s+="导出元信息：格式=";s+=quote(sv(p["format"]["version"]));s+="；导出器=";s+=quote(sv(p["exporter"]["name"]));s+="，版本=";s+=quote(sv(p["exporter"]["version"]));s+="；Lean版本=";s+=quote(sv(p["lean"]["version"]));s+="，提交=";s+=quote(sv(p["lean"]["githash"]));s+="。后续N/L/E分别为名称、宇宙层级、表达式表；N0匿名，L0为零层级。";
  }else if(kind=="str"){
   keys(p,{"pre","str"});U pre=u(p["pre"]);names.str(id,pre,sv(p["str"]));idprefix('N',id);s+="定义层级名称";s+=quote(names.render(id));s+="，在前缀";N(pre);s+="后追加字符串组件";s+=quote(sv(p["str"]));s+="。";
  }else if(kind=="num"){
   keys(p,{"pre","i"});U pre=u(p["pre"]);names.numeric(id,pre,u(p["i"]));idprefix('N',id);s+="定义层级名称";s+=quote(names.render(id));s+="，在前缀";N(pre);s+="后追加数字组件";num(s,u(p["i"]));s+="（此数字是组件值）。";
  }else if(kind=="succ"){
   idprefix('L',id);s+="宇宙层级后继succ(";L(u(p));s+=")。";
  }else if(kind=="max"||kind=="imax"){
   auto a=p.get_array().value();if(a.size()!=2)throw std::runtime_error("Binary level expected");idprefix('L',id);s+=kind;s+='(';L(u(a.at(0)));s+=',';L(u(a.at(1)));s+=')';if(kind=="imax")s+="；第二参数为零时结果为零，否则取两层级的最大值";else s+="，取两宇宙层级的最大值";s+="。";
  }else if(kind=="param"){
   idprefix('L',id);s+="以名称";name(p,true);s+="标识的宇宙层级参数。";
  }else if(kind=="bvar"){
   idprefix('E',id);s+="绑定变量bvar，de Bruijn索引=";num(s,u(p));s+="；0指使用该节点时的最内层绑定，具体绑定取决于使用路径的上下文。";
  }else if(kind=="sort"){
   idprefix('E',id);s+="Sort(";L(u(p));s+=")，宇宙层级对应的类型宇宙";if(u(p)==0)s+="，即Prop";s+="。";
  }else if(kind=="const"){
   keys(p,{"name","us"});idprefix('E',id);s+="常量引用：名称=";name(p["name"]);s+="；实例化宇宙层级=";arr(p["us"],'L');s+="。";
  }else if(kind=="app"){
   keys(p,{"fn","arg"});idprefix('E',id);s+="函数应用，以";X(u(p["fn"]));s+="为函数、";X(u(p["arg"]));s+="为实参。";
  }else if(kind=="lam"||kind=="forallE"){
   keys(p,{"name","type","body","binderInfo"});idprefix('E',id);s+=kind=="lam"?"λ函数抽象：参数名=":"Π依赖函数类型/全称类型：绑定名=";name(p["name"]);s+="，";binder(p["binderInfo"]);s+="；绑定类型=";X(u(p["type"]));s+="；主体=";X(u(p["body"]));s+="。";
  }else if(kind=="letE"){
   keys(p,{"name","type","value","body","nondep"});idprefix('E',id);s+="局部let：名称=";name(p["name"]);s+="，类型=";X(u(p["type"]));s+="，取值=";X(u(p["value"]));s+="，主体=";X(u(p["body"]));s+="；nondep=";s+=tf(p["nondep"]);s+="是elaborator标记，不能据此断定主体是否引用变量；默认导出器会把它归一化为false。";
  }else if(kind=="proj"){
   keys(p,{"typeName","idx","struct"});idprefix('E',id);s+="结构字段投影：结构类型名=";name(p["typeName"]);s+="，零起字段序号=";num(s,u(p["idx"]));s+="，被投影的结构表达式=";X(u(p["struct"]));s+="。";
  }else if(kind=="natVal"){
   auto v=sv(p);if(v.empty()||std::any_of(v.begin(),v.end(),[](char c){return c<'0'||c>'9';}))throw std::runtime_error("Invalid natVal decimal string");idprefix('E',id);s+="自然数字面量，十进制字符串=";s+=preview(v);s+="。";
  }else if(kind=="strVal"){
   idprefix('E',id);s+="字符串字面量，内容=";s+=preview(sv(p));s+="。";
  }else if(kind=="mdata"){
   keys(p,{"expr","data"});idprefix('E',id);s+="元数据包装：底层表达式=";X(u(p["expr"]));s+="；data为元数据对象，含";O data=p["data"].get_object().value();for(auto kv:data)(void)sv(kv.value);num(s,data.size());s+="个键，原对象保留在原文；元数据不作为新的逻辑断言。";
  }else if(kind=="axiom"){
   keys(p,{"name","levelParams","type","isUnsafe"});s+="公理声明（本行不带证明体）：";common(p);fieldBool(p,"isUnsafe","isUnsafe");s+="。";
  }else if(kind=="def"){
   keys(p,{"name","levelParams","type","value","hints","safety","all"});s+="定义声明：";common(p);s+="；定义值=";X(u(p["value"]));s+="；展开优先级提示hints=";
   E h=p["hints"];if(h.is_string()){auto v=sv(h);if(v!="opaque"&&v!="abbrev")throw std::runtime_error("Unknown hints");s+=v;}else{keys(h,{"regular"});s+="regular(";U height=u(h["regular"]);if(height>UINT32_MAX)throw std::runtime_error("regular hint exceeds UInt32");num(s,height);s+=')';}
   auto safe=sv(p["safety"]);if(safe!="unsafe"&&safe!="safe"&&safe!="partial")throw std::runtime_error("Unknown safety");s+="；safety=";s+=safe;group(p);s+="。hints影响展开次序，不禁止内核为类型检查展开；all不是依赖全集。";
  }else if(kind=="opaque"){
   keys(p,{"name","levelParams","type","value","all","isUnsafe"});s+="不透明常量声明：";common(p);s+="；给定值=";X(u(p["value"]));fieldBool(p,"isUnsafe","isUnsafe");group(p);s+="。其opaque声明性质与def的hints字段不同。";
  }else if(kind=="thm"){
   keys(p,{"name","levelParams","type","value","all"});s+="定理声明：";common(p);s+="；证明项=";X(u(p["value"]));group(p);s+="。本行记录所给证明项，注释程序不替代内核验证。";
  }else if(kind=="quot"){
   keys(p,{"name","levelParams","type","kind"});s+="商类型包中的声明：";common(p);auto k=sv(p["kind"]);s+="；kind=";s+=k;
   if(k=="type")s+="（商类型）";else if(k=="ctor")s+="（商构造器）";else if(k=="lift")s+="（提升操作）";else if(k=="ind")s+="（归纳操作）";else throw std::runtime_error("Unknown quotient kind");s+="。";
  }else if(kind=="inductive"){
   keys(p,{"types","ctors","recs"});s+="归纳/互归纳声明组：类型";num(s,p["types"].get_array().value().size());s+="个，构造器";num(s,p["ctors"].get_array().value().size());s+="个，递归器";num(s,p["recs"].get_array().value().size());s+="个。";
   A types=p["types"].get_array().value();for(E t:types){
    keys(t,{"name","levelParams","type","numParams","numIndices","all","ctors","numNested","isRec","isUnsafe","isReflexive"});s+="【归纳类型：";common(t);fieldNat(t,"numParams","参数数");fieldNat(t,"numIndices","指标数");group(t);s+="；构造器名称=";arr(t["ctors"],'N');fieldNat(t,"numNested","嵌套归纳辅助类型数");fieldBool(t,"isRec","递归出现isRec");fieldBool(t,"isUnsafe","isUnsafe");fieldBool(t,"isReflexive","构造器接受返回该类型的函数isReflexive");s+="】";
   }
   A ctors=p["ctors"].get_array().value();for(E t:ctors){
    keys(t,{"name","levelParams","type","induct","cidx","numParams","numFields","isUnsafe"});s+="【构造器：";common(t);s+="；所属归纳类型=";name(t["induct"]);fieldNat(t,"cidx","构造器序号");fieldNat(t,"numParams","参数数");fieldNat(t,"numFields","字段数");fieldBool(t,"isUnsafe","isUnsafe");s+="】";
   }
   A recs=p["recs"].get_array().value();for(E t:recs){
    keys(t,{"name","levelParams","type","all","numParams","numIndices","numMotives","numMinors","rules","k","isUnsafe"});s+="【递归器：";common(t);group(t);fieldNat(t,"numParams","参数数");fieldNat(t,"numIndices","指标数");fieldNat(t,"numMotives","目标族数");fieldNat(t,"numMinors","次要前提数");fieldBool(t,"k","支持K-like归约k");fieldBool(t,"isUnsafe","isUnsafe");s+="；计算规则=";
    A rules=t["rules"].get_array().value();for(E r:rules){keys(r,{"ctor","nfields","rhs"});s+='{';name(r["ctor"]);s+="，字段数=";num(s,u(r["nfields"]));s+="，右端表达式=";X(u(r["rhs"]));s+='}';}s+="】";
   }
  }else throw std::runtime_error("Unknown top-level variant: "+std::string(kind));
  if(table=='L')nextL++;if(table=='E')nextE++;counts[std::string(kind)]++;lines++;s+='\n';return s;
 }
};

void zcheck(size_t rc){if(ZSTD_isError(rc))throw std::runtime_error(std::string("zstd: ")+ZSTD_getErrorName(rc));}
class Output{
 bool rawStdout;fs::path dir;int level,workers;U threshold;
 ZSTD_CCtx *c=nullptr;FILE *file=nullptr;std::vector<char> compressed;
 std::string buffer;U currentFirst=0,currentLast=0,totalRows=0,partRows=0,partRaw=0,partAnn=0,partCompressed=0,partNo=0,totalCompressed=0;
 Hash *rawHash=nullptr,*compressedHash=nullptr;std::ofstream manifest;std::string partName;
 void writeCompressed(size_t n){if(n){if(fwrite(compressed.data(),1,n,file)!=n)throw std::runtime_error("Output write failed");compressedHash->add(compressed.data(),n);partCompressed+=n;}}
 void flush(bool end){
  if(rawStdout){if(!buffer.empty()&&fwrite(buffer.data(),1,buffer.size(),stdout)!=buffer.size())throw std::runtime_error("stdout write failed");buffer.clear();return;}
  ZSTD_inBuffer in{buffer.data(),buffer.size(),0};ZSTD_EndDirective mode=end?ZSTD_e_end:ZSTD_e_continue;size_t remaining;
  do{ZSTD_outBuffer out{compressed.data(),compressed.size(),0};remaining=ZSTD_compressStream2(c,&out,&in,mode);zcheck(remaining);writeCompressed(out.pos);}while(in.pos<in.size||(end&&remaining));buffer.clear();
 }
 void openPart(U line){
  currentFirst=line;currentLast=line;partRows=partRaw=partAnn=partCompressed=0;partNo++;
  char fn[80];snprintf(fn,sizeof fn,"solution_annotated.part%03llu.txt.zst",(unsigned long long)partNo);partName=fn;file=fopen((dir/(partName+".partial")).c_str(),"wb");if(!file)throw std::runtime_error("Cannot create shard");
  c=ZSTD_createCCtx();if(!c)throw std::runtime_error("Cannot create compressor");zcheck(ZSTD_CCtx_setParameter(c,ZSTD_c_compressionLevel,level));zcheck(ZSTD_CCtx_setParameter(c,ZSTD_c_checksumFlag,1));zcheck(ZSTD_CCtx_setParameter(c,ZSTD_c_nbWorkers,workers));rawHash=new Hash;compressedHash=new Hash;
 }
 void closePart(){if(!file)return;flush(true);if(fclose(file))throw std::runtime_error("Cannot close output");file=nullptr;ZSTD_freeCCtx(c);c=nullptr;std::string rh=rawHash->finish(),ch=compressedHash->finish();delete rawHash;delete compressedHash;rawHash=compressedHash=nullptr;
  if(partCompressed>(400ull<<20))throw std::runtime_error("Compressed shard exceeds 400 MiB maximum");fs::rename(dir/(partName+".partial"),dir/partName);totalCompressed+=partCompressed;
  manifest<<"{\"file\":"<<quote(partName)<<",\"first_line\":"<<currentFirst<<",\"last_line\":"<<currentLast<<",\"records\":"<<partRows<<",\"original_bytes\":"<<partRaw<<",\"original_sha256\":"<<quote(rh)<<",\"annotated_bytes\":"<<partAnn<<",\"compressed_bytes\":"<<partCompressed<<",\"compressed_sha256\":"<<quote(ch)<<"}\n";manifest.flush();
  std::cerr<<"{\"event\":\"shard_completed\",\"file\":"<<quote(partName)<<",\"last_line\":"<<currentLast<<",\"compressed_bytes\":"<<partCompressed<<"}\n";
 }
 public:
 Output(bool stdoutMode,const fs::path &directory,int lvl,int w,U limit):rawStdout(stdoutMode),dir(directory),level(lvl),workers(w),threshold(limit),compressed(2<<20){buffer.reserve(8<<20);if(!rawStdout){manifest.open(dir/"parts.jsonl",std::ios::out|std::ios::trunc);if(!manifest)throw std::runtime_error("Cannot create manifest");}}
 ~Output(){if(file)fclose(file);if(c)ZSTD_freeCCtx(c);delete rawHash;delete compressedHash;}
 void row(U line,std::string_view annotation,std::string_view original,bool lf){
  if(!rawStdout&&!file)openPart(line);
  buffer.append(annotation);buffer.append(original);if(lf)buffer+='\n';totalRows++;
  if(!rawStdout){partRows++;currentLast=line;partRaw+=original.size()+lf;partAnn+=annotation.size()+original.size()+lf;rawHash->add(original.data(),original.size());if(lf)rawHash->add("\n",1);}
  if(buffer.size()>=(8<<20)){flush(false);if(!rawStdout&&partCompressed>=threshold)closePart();}
 }
 void finish(){if(rawStdout){flush(false);fflush(stdout);}else closePart();}
 U compressed_bytes()const{return totalCompressed+(file?partCompressed:0);}U parts()const{return partNo;}
};

int main(int argc,char **argv){
 fs::path outdir,summary,state;bool toStdout=false;int level=1,workers=2;U maxLines=0,shardMiB=320;std::string expectedHash;U expectedBytes=0;
 for(int i=1;i<argc;i++){std::string a=argv[i];auto val=[&](){if(++i>=argc)throw std::runtime_error("Missing argument");return std::string(argv[i]);};if(a=="--output-dir")outdir=val();else if(a=="--summary")summary=val();else if(a=="--state-dir")state=val();else if(a=="--stdout")toStdout=true;else if(a=="--level")level=std::stoi(val());else if(a=="--workers")workers=std::stoi(val());else if(a=="--max-lines")maxLines=std::stoull(val());else if(a=="--shard-mib")shardMiB=std::stoull(val());else if(a=="--expected-sha256")expectedHash=val();else if(a=="--expected-bytes")expectedBytes=std::stoull(val());else{std::cerr<<"Unknown option: "<<a<<'\n';return 2;}}
 if(state.empty()||(!toStdout&&outdir.empty())||summary.empty()){std::cerr<<"Usage: annotate_ndjson --state-dir NEW_DIR --summary FILE (--stdout | --output-dir NEW_DIR) [--level 1 --workers 2 --shard-mib 320 --expected-sha256 HASH --expected-bytes N]\n";return 2;}
 U lines=0,bytes=0,annBytes=0;auto start=Clock::now();
 try{
  if(fs::exists(state)&&!fs::is_empty(state))throw std::runtime_error("State directory must be new or empty");fs::create_directories(state);
  if(!toStdout){if(fs::exists(outdir)&&!fs::is_empty(outdir))throw std::runtime_error("Output directory must be new or empty");fs::create_directories(outdir);}
  Explainer ex(state);Output output(toStdout,outdir,level,workers,shardMiB<<20);Hash inputHash;simdjson::dom::parser parser;std::string line;line.reserve(1<<20);std::ios::sync_with_stdio(false);std::cin.tie(nullptr);
  auto last=Clock::now();U lastReport=0;bool stopped=false;
  while(std::getline(std::cin,line)){
   bool lf=!std::cin.eof();lines++;inputHash.add(line.data(),line.size());if(lf)inputHash.add("\n",1);bytes+=line.size()+lf;
   E doc=parser.parse(line);const std::string &comment=ex.explain(doc,lines);annBytes+=comment.size()+line.size()+lf;output.row(lines,comment,line,lf);
   if(bytes-lastReport>=(64ull<<20)){lastReport=bytes;auto now=Clock::now();if(std::chrono::duration<double>(now-last).count()>=10){last=now;std::cerr<<"{\"event\":\"progress\",\"lines\":"<<lines<<",\"source_bytes\":"<<bytes<<",\"annotated_bytes\":"<<annBytes<<",\"name_store_bytes\":"<<ex.name_bytes()<<",\"elapsed_seconds\":"<<std::chrono::duration<double>(now-start).count()<<"}\n";}}
   if(maxLines&&lines>=maxLines){stopped=true;break;}
  }
  if(std::cin.bad())throw std::runtime_error("Input read error");std::string hash=inputHash.finish();bool full=!stopped;
  if(full&&expectedBytes&&bytes!=expectedBytes)throw std::runtime_error("Source byte count mismatch");if(full&&!expectedHash.empty()&&hash!=expectedHash)throw std::runtime_error("Source SHA256 mismatch");
  output.finish();std::ofstream f(summary);if(!f)throw std::runtime_error("Cannot write summary");
  f<<"{\n\"success\":true,\n\"input_fully_consumed\":"<<(full?"true":"false")<<",\n\"records\":"<<lines<<",\n\"original_bytes\":"<<bytes<<",\n\"original_sha256\":"<<quote(hash)<<",\n\"annotated_bytes\":"<<annBytes<<",\n\"compressed_bytes\":"<<output.compressed_bytes()<<",\n\"parts\":"<<output.parts()<<",\n\"name_definitions\":"<<ex.name_count()<<",\n\"level_definitions\":"<<ex.level_count()<<",\n\"expression_definitions\":"<<ex.expr_count()<<",\n\"name_store_bytes\":"<<ex.name_bytes()<<",\n\"unknown_record_types\":0,\n\"reference_checks\":\"All typed N/L/E references point to earlier definitions; sequential IDs validated. This is not kernel type checking.\",\n\"elapsed_seconds\":"<<std::chrono::duration<double>(Clock::now()-start).count()<<",\n\"counts\":{";bool first=true;for(auto &[k,v]:ex.counts){if(!first)f<<',';first=false;f<<quote(k)<<':'<<v;}f<<"}\n}\n";f.close();std::cerr<<"{\"event\":\"complete\",\"records\":"<<lines<<",\"source_bytes\":"<<bytes<<",\"elapsed_seconds\":"<<std::chrono::duration<double>(Clock::now()-start).count()<<"}\n";
 }catch(const std::exception &e){std::cerr<<"{\"event\":\"error\",\"line\":"<<lines<<",\"source_bytes\":"<<bytes<<",\"message\":"<<quote(e.what())<<"}\n";return 1;}
 return 0;
}
