// Independent streaming verifier/restorer for the annotated NDJSON volumes.
// Parses only the small manifest with simdjson. Source JSON receives a basic
// object-line shape check, NOT semantic JSON validation or Lean kernel checking.
#include "vendor/simdjson.h"
#include <openssl/evp.h>
#include <zstd.h>
#include <algorithm>
#include <array>
#include <charconv>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <limits>
#include <memory>
#include <set>
#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>
#include <cerrno>
#include <fcntl.h>
#include <unistd.h>

namespace fs = std::filesystem;
using U64 = uint64_t;
using Clock = std::chrono::steady_clock;
constexpr U64 FULL_BYTES = 61570595788ULL;
constexpr const char* FULL_SHA = "5ea74b912147c5c93cc2b6d70cc727cf908df2f62ac6a20480a3fa02f6be244e";
constexpr size_t BLOCK = 4U << 20;
constexpr size_t RAW_BATCH = 8U << 20;

std::string json_quote(std::string_view v) {
    std::string out;
    out.reserve(v.size() + 2);
    out.push_back('"');
    constexpr char hex[] = "0123456789abcdef";
    for (unsigned char c : v) {
        if (c == '"' || c == '\\') { out.push_back('\\'); out.push_back(c); }
        else if (c < 32) { out += "\\u00"; out.push_back(hex[c >> 4]); out.push_back(hex[c & 15]); }
        else out.push_back(c);
    }
    out.push_back('"');
    return out;
}

U64 parse_u64(std::string_view text, const char* what) {
    U64 n = 0;
    auto result = std::from_chars(text.data(), text.data() + text.size(), n);
    if (text.empty() || result.ec != std::errc() || result.ptr != text.data() + text.size())
        throw std::runtime_error(std::string("Invalid nonnegative integer for ") + what);
    return n;
}

U64 add_checked(U64 a, U64 b, const char* what) {
    if (b > std::numeric_limits<U64>::max() - a)
        throw std::runtime_error(std::string("Integer overflow: ") + what);
    return a + b;
}

std::string digest_text(std::string_view text) {
    if (text.size() != 64) throw std::runtime_error("SHA-256 must have exactly 64 hexadecimal digits");
    std::string s(text);
    for (char& c : s) {
        if (c >= 'A' && c <= 'F') c += 'a' - 'A';
        else if (!(c >= '0' && c <= '9') && !(c >= 'a' && c <= 'f'))
            throw std::runtime_error("Invalid SHA-256 hexadecimal digit");
    }
    return s;
}

class Sha256 {
    EVP_MD_CTX* ctx_ = EVP_MD_CTX_new();
    bool finished_ = false;
public:
    Sha256() {
        if (!ctx_ || EVP_DigestInit_ex(ctx_, EVP_sha256(), nullptr) != 1)
            throw std::runtime_error("Cannot initialize OpenSSL SHA-256");
    }
    ~Sha256() { EVP_MD_CTX_free(ctx_); }
    Sha256(const Sha256&) = delete;
    Sha256& operator=(const Sha256&) = delete;
    void append(const void* data, size_t size) {
        if (size && EVP_DigestUpdate(ctx_, data, size) != 1)
            throw std::runtime_error("Cannot update SHA-256");
    }
    std::string finish() {
        if (finished_) throw std::runtime_error("SHA-256 was already finalized");
        finished_ = true;
        unsigned char bytes[EVP_MAX_MD_SIZE];
        unsigned int size = 0;
        if (EVP_DigestFinal_ex(ctx_, bytes, &size) != 1 || size != 32)
            throw std::runtime_error("Cannot finish SHA-256");
        constexpr char hex[] = "0123456789abcdef";
        std::string out(64, '0');
        for (unsigned int i = 0; i < 32; ++i) { out[2*i] = hex[bytes[i] >> 4]; out[2*i+1] = hex[bytes[i] & 15]; }
        return out;
    }
};

struct Part {
    std::string file, original_sha, compressed_sha;
    U64 first = 0, last = 0, records = 0, original_bytes = 0, annotated_bytes = 0, compressed_bytes = 0;
};

struct Manifest {
    std::vector<Part> parts;
    std::string sha;
    U64 records = 0, original_bytes = 0, annotated_bytes = 0, compressed_bytes = 0;
};

Manifest read_manifest(const fs::path& path) {
    std::ifstream stream(path, std::ios::binary);
    if (!stream) throw std::runtime_error("Cannot open manifest: " + path.string());
    std::string text((std::istreambuf_iterator<char>(stream)), std::istreambuf_iterator<char>());
    if (stream.bad()) throw std::runtime_error("Cannot read manifest");
    Manifest manifest;
    Sha256 hash;
    hash.append(text.data(), text.size());
    manifest.sha = hash.finish();
    simdjson::dom::parser parser;
    const std::set<std::string_view> expected_fields = {
        "file", "first_line", "last_line", "records", "original_bytes", "original_sha256",
        "annotated_bytes", "compressed_bytes", "compressed_sha256"
    };
    std::set<std::string> seen_files;
    U64 next = 1;
    size_t offset = 0;
    while (offset < text.size()) {
        size_t end = text.find('\n', offset);
        if (end == std::string::npos) end = text.size();
        std::string_view line(text.data() + offset, end - offset);
        offset = end + (end < text.size());
        if (line.empty()) throw std::runtime_error("Blank manifest line");
        auto obj = parser.parse(line).get_object().value();
        std::set<std::string_view> found;
        for (auto field : obj) {
            if (!expected_fields.count(field.key) || !found.insert(field.key).second)
                throw std::runtime_error("Unknown or duplicate manifest field: " + std::string(field.key));
        }
        if (found != expected_fields) throw std::runtime_error("Missing manifest fields");
        Part part;
        part.file = std::string(obj["file"].get_string().value());
        if (part.file.empty() || part.file.find('\0') != std::string::npos ||
            part.file.find('/') != std::string::npos || part.file.find('\\') != std::string::npos ||
            part.file == "." || part.file == "..")
            throw std::runtime_error("Manifest file must be a plain filename");
        if (!seen_files.insert(part.file).second) throw std::runtime_error("Repeated volume filename");
        part.first = obj["first_line"].get_uint64().value();
        part.last = obj["last_line"].get_uint64().value();
        part.records = obj["records"].get_uint64().value();
        part.original_bytes = obj["original_bytes"].get_uint64().value();
        part.annotated_bytes = obj["annotated_bytes"].get_uint64().value();
        part.compressed_bytes = obj["compressed_bytes"].get_uint64().value();
        part.original_sha = digest_text(obj["original_sha256"].get_string().value());
        part.compressed_sha = digest_text(obj["compressed_sha256"].get_string().value());
        if (!part.records || part.first != next || part.last < part.first ||
            part.last - part.first != part.records - 1)
            throw std::runtime_error("Manifest line ranges are not globally consecutive");
        if (!part.original_bytes || !part.compressed_bytes || part.annotated_bytes <= part.original_bytes)
            throw std::runtime_error("Invalid manifest byte counts");
        next = add_checked(part.last, 1, "next source line");
        manifest.records = add_checked(manifest.records, part.records, "manifest records");
        manifest.original_bytes = add_checked(manifest.original_bytes, part.original_bytes, "manifest source bytes");
        manifest.annotated_bytes = add_checked(manifest.annotated_bytes, part.annotated_bytes, "manifest annotated bytes");
        manifest.compressed_bytes = add_checked(manifest.compressed_bytes, part.compressed_bytes, "manifest compressed bytes");
        manifest.parts.push_back(std::move(part));
    }
    if (manifest.parts.empty()) throw std::runtime_error("Empty manifest");
    return manifest;
}

void write_all(int fd, const char* data, size_t size) {
    while (size) {
        ssize_t n = ::write(fd, data, size);
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0) throw std::runtime_error("Restore write failed: " + std::string(std::strerror(errno)));
        data += n;
        size -= static_cast<size_t>(n);
    }
}

class RawSink {
    Sha256 global_hash_;
    Sha256* part_hash_ = nullptr;
    std::vector<char> bytes_;
    size_t used_ = 0;
    int restore_fd_ = -1;
    fs::path restore_final_, restore_partial_;
public:
    U64 total_bytes = 0, part_bytes = 0;
    explicit RawSink(const fs::path& restore) : bytes_(RAW_BATCH) {
        if (!restore.empty()) {
            restore_final_ = restore;
            restore_partial_ = fs::path(restore.string() + ".partial");
            if (fs::exists(restore_final_)) throw std::runtime_error("Refusing to overwrite restore destination");
            restore_fd_ = ::open(restore_partial_.c_str(), O_WRONLY | O_CREAT | O_EXCL, 0600);
            if (restore_fd_ < 0) throw std::runtime_error("Cannot create exclusive restore .partial file: " + std::string(std::strerror(errno)));
        }
    }
    ~RawSink() { if (restore_fd_ >= 0) ::close(restore_fd_); }
    void start_part(Sha256& hash) {
        if (used_) throw std::runtime_error("Internal unflushed volume boundary");
        part_hash_ = &hash;
        part_bytes = 0;
    }
    void flush() {
        if (!used_) return;
        global_hash_.append(bytes_.data(), used_);
        part_hash_->append(bytes_.data(), used_);
        if (restore_fd_ >= 0) write_all(restore_fd_, bytes_.data(), used_);
        used_ = 0;
    }
    void append(const char* data, size_t size) {
        total_bytes += size;
        part_bytes += size;
        while (size) {
            size_t n = std::min(size, bytes_.size() - used_);
            std::memcpy(bytes_.data() + used_, data, n);
            used_ += n;
            data += n;
            size -= n;
            if (used_ == bytes_.size()) flush();
        }
    }
    std::string finish_hash() { flush(); return global_hash_.finish(); }
    std::string partial_path() const { return restore_partial_.string(); }
    void commit_restore() {
        if (restore_fd_ < 0) return;
        if (::fsync(restore_fd_)) throw std::runtime_error("Cannot sync restored bytes");
        int fd = restore_fd_;
        restore_fd_ = -1;
        if (::close(fd)) throw std::runtime_error("Cannot close restored file");
        // An atomic, no-overwrite installation in the same directory. Keeping
        // the partial file on failure gives the user a concrete recovery point.
        if (::link(restore_partial_.c_str(), restore_final_.c_str()))
            throw std::runtime_error("Cannot install restore file without overwriting: " + std::string(std::strerror(errno)));
        if (::unlink(restore_partial_.c_str()))
            throw std::runtime_error("Restoration succeeded but cannot remove partial hard link");
    }
};

inline bool json_space(unsigned char c) { return c == ' ' || c == '\t' || c == '\r'; }
constexpr std::string_view COMMENT_PREFIX = "-- @line ";

// Only boundary-crossing physical lines use the incremental state below.
// No full physical line is copied or retained; even huge lines stay bounded.
class CommentFragment {
    size_t prefix_ = 0;
    U64 value_ = 0, expected_ = 0;
    bool digits_ = false, body_ = false, nonempty_ = false;
public:
    void start(U64 expected) { prefix_ = 0; value_ = 0; expected_ = expected; digits_ = body_ = nonempty_ = false; }
    void consume(const char* p, size_t n) {
        const char* end = p + n;
        while (p < end && prefix_ < COMMENT_PREFIX.size()) {
            if (*p++ != COMMENT_PREFIX[prefix_++]) throw std::runtime_error("Bad annotation prefix");
        }
        while (p < end && !body_) {
            unsigned char c = *p++;
            if (c >= '0' && c <= '9') {
                if (!digits_ && c == '0') throw std::runtime_error("Noncanonical annotation line number");
                digits_ = true;
                if (value_ > (std::numeric_limits<U64>::max() - (c - '0')) / 10)
                    throw std::runtime_error("Annotation line number overflow");
                value_ = value_ * 10 + (c - '0');
            } else if (c == ' ' && digits_) {
                if (value_ != expected_) throw std::runtime_error("Annotation line number is not globally consecutive");
                body_ = true;
            } else throw std::runtime_error("Malformed annotation line number or separator");
        }
        if (body_ && !nonempty_) {
            while (p < end) { if (!json_space(static_cast<unsigned char>(*p++))) { nonempty_ = true; break; } }
        }
    }
    void finish() const {
        if (prefix_ != COMMENT_PREFIX.size() || !body_ || !nonempty_)
            throw std::runtime_error("Missing or empty annotation text");
    }
};

class OriginalFragment {
    bool first_ = false;
    char last_ = 0;
public:
    void start() { first_ = false; last_ = 0; }
    void consume(const char* p, size_t n) {
        const char* end = p + n;
        if (!first_) {
            while (p < end && json_space(static_cast<unsigned char>(*p))) ++p;
            if (p < end) {
                if (*p != '{') throw std::runtime_error("Original line does not start with a JSON object");
                first_ = true;
            }
        }
        while (end > p && json_space(static_cast<unsigned char>(end[-1]))) --end;
        if (end > p) last_ = end[-1];
    }
    void finish() const {
        if (!first_ || last_ != '}') throw std::runtime_error("Original line lacks a complete JSON object boundary");
    }
};

class PairScanner {
    RawSink& sink_;
    bool want_comment_ = true, fragment_ = false;
    CommentFragment comment_fragment_;
    OriginalFragment original_fragment_;
    U64 expected_line_;
    void annotation(const char* p, size_t n) {
        if (n <= COMMENT_PREFIX.size() || std::memcmp(p, COMMENT_PREFIX.data(), COMMENT_PREFIX.size()))
            throw std::runtime_error("Bad annotation prefix");
        p += COMMENT_PREFIX.size();
        const char* end = p + n - COMMENT_PREFIX.size();
        if (*p < '1' || *p > '9') throw std::runtime_error("Noncanonical annotation line number");
        U64 line = 0;
        auto result = std::from_chars(p, end, line);
        if (result.ec != std::errc() || result.ptr == end || *result.ptr != ' ')
            throw std::runtime_error("Malformed annotation line number or separator");
        if (line != expected_line_) throw std::runtime_error("Annotation line number is not globally consecutive");
        p = result.ptr + 1;
        while (p < end && json_space(static_cast<unsigned char>(*p))) ++p;
        if (p == end) throw std::runtime_error("Empty annotation text");
    }
    void original(const char* p, size_t n) {
        const char* end = p + n;
        while (p < end && json_space(static_cast<unsigned char>(*p))) ++p;
        while (end > p && json_space(static_cast<unsigned char>(end[-1]))) --end;
        if (end - p < 2 || *p != '{' || end[-1] != '}')
            throw std::runtime_error("Original line lacks a JSON object boundary");
    }
    void complete_original(bool lf) {
        ++records;
        ++expected_line_;
        last_original_has_lf = lf;
    }
public:
    U64 records = 0, annotated_bytes = 0;
    bool last_original_has_lf = true;
    PairScanner(RawSink& sink, U64 expected) : sink_(sink), expected_line_(expected) {}
    U64 current_line() const { return expected_line_; }
    void feed(const char* data, size_t size) {
        annotated_bytes += size;
        const char* p = data;
        const char* end = data + size;
        while (p < end) {
            const char* nl = static_cast<const char*>(std::memchr(p, '\n', end - p));
            if (!nl) {
                if (!fragment_) {
                    if (want_comment_) comment_fragment_.start(expected_line_);
                    else original_fragment_.start();
                    fragment_ = true;
                }
                if (want_comment_) comment_fragment_.consume(p, end - p);
                else { original_fragment_.consume(p, end - p); sink_.append(p, end - p); }
                return;
            }
            size_t n = nl - p;
            if (want_comment_) {
                if (fragment_) { comment_fragment_.consume(p, n); comment_fragment_.finish(); }
                else annotation(p, n);
            } else {
                if (fragment_) { original_fragment_.consume(p, n); original_fragment_.finish(); }
                else original(p, n);
                sink_.append(p, n + 1); // Preserve the actual LF byte, never manufacture one.
                complete_original(true);
            }
            fragment_ = false;
            want_comment_ = !want_comment_;
            p = nl + 1;
        }
    }
    void finish_part(bool final_part) {
        if (fragment_) {
            if (want_comment_) throw std::runtime_error("Unterminated annotation without its original row");
            if (!final_part) throw std::runtime_error("A non-final volume ends with an original row lacking LF");
            original_fragment_.finish();
            complete_original(false);
            want_comment_ = true;
            fragment_ = false;
        }
        if (!want_comment_) throw std::runtime_error("Annotation is missing its original row");
    }
};

struct Options {
    fs::path manifest, part_dir, report, restore;
    U64 expected_bytes = FULL_BYTES, expected_records = 0;
    std::string expected_sha = FULL_SHA;
    size_t io_block = BLOCK;
};

struct FileCloser { void operator()(FILE* file) const { if (file) std::fclose(file); } };

void usage() {
    std::cerr << "Usage: verify_annotations --manifest parts.jsonl [--part-dir DIR] [--report FILE]\n"
                 "       [--restore NEW_FILE] [--expected-bytes N --expected-sha256 SHA256]\n"
                 "       [--expected-records N] [--io-buffer-bytes N]\n"
                 "Defaults verify the complete MIT solution.ndjson (61570595788 bytes).\n"
                 "Volumes default to the manifest directory. --restore writes only original bytes.\n"
                 "No source file is written unless --restore is explicitly provided.\n";
}

Options options(int argc, char** argv) {
    Options opt;
    bool supplied_bytes = false, supplied_sha = false;
    for (int i = 1; i < argc; ++i) {
        std::string key = argv[i];
        auto val = [&]() -> std::string { if (++i >= argc) throw std::runtime_error("Missing argument for " + key); return argv[i]; };
        if (key == "--manifest") opt.manifest = val();
        else if (key == "--part-dir") opt.part_dir = val();
        else if (key == "--report") opt.report = val();
        else if (key == "--restore") opt.restore = val();
        else if (key == "--expected-bytes") { opt.expected_bytes = parse_u64(val(), "--expected-bytes"); supplied_bytes = true; }
        else if (key == "--expected-sha256") { opt.expected_sha = digest_text(val()); supplied_sha = true; }
        else if (key == "--expected-records") opt.expected_records = parse_u64(val(), "--expected-records");
        else if (key == "--io-buffer-bytes") {
            U64 value = parse_u64(val(), "--io-buffer-bytes");
            if (value < 64 || value > (64U << 20)) throw std::runtime_error("I/O buffer must be between 64 bytes and 64 MiB");
            opt.io_block = static_cast<size_t>(value);
        } else if (key == "--help" || key == "-h") { usage(); std::exit(0); }
        else throw std::runtime_error("Unknown option: " + key);
    }
    if (opt.manifest.empty()) throw std::runtime_error("--manifest is required");
    if (supplied_bytes != supplied_sha) throw std::runtime_error("Override expected bytes and SHA-256 together");
    if (opt.part_dir.empty()) opt.part_dir = opt.manifest.parent_path();
    if (opt.part_dir.empty()) opt.part_dir = ".";
    if (!opt.report.empty() && fs::exists(opt.report)) throw std::runtime_error("Refusing to overwrite report file");
    return opt;
}

void save_report(const fs::path& path, const std::string& text) {
    if (path.empty()) return;
    int fd = ::open(path.c_str(), O_WRONLY | O_CREAT | O_EXCL, 0600);
    if (fd < 0) throw std::runtime_error("Cannot create report: " + std::string(std::strerror(errno)));
    try { write_all(fd, text.data(), text.size()); }
    catch (...) { ::close(fd); throw; }
    if (::close(fd)) throw std::runtime_error("Cannot close report");
}

int main(int argc, char** argv) {
    Options opt;
    U64 completed_parts = 0, completed_records = 0, compressed_total = 0, annotated_total = 0;
    U64 current_line = 1;
    std::string current_file;
    const auto start = Clock::now();
    std::unique_ptr<RawSink> sink;
    try {
        opt = options(argc, argv);
        Manifest manifest = read_manifest(opt.manifest);
        if (manifest.original_bytes != opt.expected_bytes) throw std::runtime_error("Manifest source byte total differs from expected source");
        if (opt.expected_records && manifest.records != opt.expected_records) throw std::runtime_error("Manifest record total differs from expected source");
        sink = std::make_unique<RawSink>(opt.restore);
        std::vector<char> input(opt.io_block), output(opt.io_block);
        std::unique_ptr<ZSTD_DCtx, decltype(&ZSTD_freeDCtx)> decoder(ZSTD_createDCtx(), ZSTD_freeDCtx);
        if (!decoder) throw std::runtime_error("Cannot allocate zstd decompressor");
        bool last_has_lf = true;
        U64 total_frames = 0;
        auto last_progress = start;
        for (size_t i = 0; i < manifest.parts.size(); ++i) {
            const Part& part = manifest.parts[i];
            current_file = part.file;
            current_line = part.first;
            const fs::path file_path = opt.part_dir / part.file;
            if (fs::file_size(file_path) != part.compressed_bytes) throw std::runtime_error("Volume compressed byte count differs from manifest");
            std::unique_ptr<FILE, FileCloser> file(std::fopen(file_path.c_str(), "rb"));
            if (!file) throw std::runtime_error("Cannot open volume");
            Sha256 compressed_hash, original_hash;
            sink->start_part(original_hash);
            PairScanner scanner(*sink, part.first);
            size_t reset = ZSTD_DCtx_reset(decoder.get(), ZSTD_reset_session_only);
            if (ZSTD_isError(reset)) throw std::runtime_error(ZSTD_getErrorName(reset));
            U64 read_bytes = 0, frames = 0;
            size_t last_result = 1;
            for (;;) {
                size_t n = std::fread(input.data(), 1, input.size(), file.get());
                if (!n) {
                    if (std::ferror(file.get())) throw std::runtime_error("Volume read failed");
                    break;
                }
                read_bytes += n;
                if (read_bytes > part.compressed_bytes) throw std::runtime_error("Volume grew during verification");
                compressed_hash.append(input.data(), n);
                ZSTD_inBuffer in{input.data(), n, 0};
                bool drain = false;
                do {
                    size_t before = in.pos;
                    ZSTD_outBuffer out{output.data(), output.size(), 0};
                    last_result = ZSTD_decompressStream(decoder.get(), &out, &in);
                    if (ZSTD_isError(last_result)) throw std::runtime_error(std::string("zstd decompression failed: ") + ZSTD_getErrorName(last_result));
                    if (out.pos) {
                        if (scanner.annotated_bytes > part.annotated_bytes || out.pos > part.annotated_bytes - scanner.annotated_bytes)
                            throw std::runtime_error("Decompressed annotation exceeds manifest byte count");
                        try { scanner.feed(output.data(), out.pos); }
                        catch (...) { current_line = scanner.current_line(); throw; }
                        current_line = scanner.current_line();
                    }
                    if (!last_result) ++frames;
                    drain = out.pos == out.size && last_result != 0;
                    if (in.pos == before && !out.pos) {
                        if (in.pos < in.size) throw std::runtime_error("zstd made no progress on available input");
                        drain = false;
                    }
                } while (in.pos < in.size || drain);
                auto now = Clock::now();
                if (std::chrono::duration<double>(now - last_progress).count() >= 10.0) {
                    last_progress = now;
                    std::cerr << "{\"event\":\"verification_progress\",\"part\":" << i+1
                        << ",\"parts_total\":" << manifest.parts.size() << ",\"records\":" << completed_records + scanner.records
                        << ",\"original_bytes\":" << sink->total_bytes << ",\"elapsed_seconds\":"
                        << std::chrono::duration<double>(now - start).count() << "}\n";
                }
            }
            if (last_result || !frames) throw std::runtime_error("Truncated or empty zstd volume");
            try { scanner.finish_part(i + 1 == manifest.parts.size()); }
            catch (...) { current_line = scanner.current_line(); throw; }
            current_line = scanner.current_line();
            sink->flush();
            if (read_bytes != part.compressed_bytes) throw std::runtime_error("Compressed byte count mismatch");
            if (compressed_hash.finish() != part.compressed_sha) throw std::runtime_error("Compressed SHA-256 mismatch");
            if (scanner.annotated_bytes != part.annotated_bytes) throw std::runtime_error("Annotated byte count mismatch");
            if (sink->part_bytes != part.original_bytes) throw std::runtime_error("Restored original byte count mismatch");
            if (original_hash.finish() != part.original_sha) throw std::runtime_error("Restored original SHA-256 mismatch");
            if (scanner.records != part.records || scanner.current_line() != part.last + 1)
                throw std::runtime_error("Volume source record count or last line mismatch");
            completed_parts++;
            completed_records += scanner.records;
            compressed_total += read_bytes;
            annotated_total += scanner.annotated_bytes;
            total_frames += frames;
            last_has_lf = scanner.last_original_has_lf;
            std::cerr << "{\"event\":\"volume_verified\",\"file\":" << json_quote(part.file)
                << ",\"first_line\":" << part.first << ",\"last_line\":" << part.last
                << ",\"records\":" << scanner.records << ",\"original_bytes\":" << sink->part_bytes << "}\n";
        }
        const std::string hash = sink->finish_hash();
        if (sink->total_bytes != opt.expected_bytes || sink->total_bytes != manifest.original_bytes)
            throw std::runtime_error("Global original byte count mismatch");
        if (hash != opt.expected_sha) throw std::runtime_error("Global original SHA-256 mismatch");
        if (completed_records != manifest.records) throw std::runtime_error("Global source record count mismatch");
        sink->commit_restore();
        double elapsed = std::chrono::duration<double>(Clock::now() - start).count();
        std::string report = "{\n  \"success\": true,\n  \"verifier\": \"verify_annotations/1.0\",\n  \"manifest\": " + json_quote(opt.manifest.string()) +
            ",\n  \"manifest_sha256\": " + json_quote(manifest.sha) + ",\n  \"parts_verified\": " + std::to_string(completed_parts) +
            ",\n  \"zstd_frames\": " + std::to_string(total_frames) + ",\n  \"records\": " + std::to_string(completed_records) +
            ",\n  \"first_line\": 1,\n  \"last_line\": " + std::to_string(completed_records) +
            ",\n  \"original_bytes\": " + std::to_string(sink->total_bytes) + ",\n  \"original_sha256\": " + json_quote(hash) +
            ",\n  \"expected_original_bytes\": " + std::to_string(opt.expected_bytes) + ",\n  \"expected_original_sha256\": " + json_quote(opt.expected_sha) +
            ",\n  \"compressed_bytes\": " + std::to_string(compressed_total) + ",\n  \"annotated_bytes\": " + std::to_string(annotated_total) +
            ",\n  \"last_original_line_has_lf\": " + (last_has_lf ? "true" : "false") +
            ",\n  \"restored_file\": " + (opt.restore.empty() ? "null" : json_quote(opt.restore.string())) +
            ",\n  \"checks\": [\"all compressed sizes and SHA-256 values\", \"all original volume sizes and SHA-256 values\", \"all annotated byte counts\", \"one nonempty annotation per original row\", \"globally consecutive source line numbers\", \"basic JSON object-line boundaries\", \"all manifest record ranges and counts\", \"global original byte count and SHA-256\"],\n"
            "  \"full_json_semantic_validation\": false,\n  \"lean_kernel_verification\": false,\n  \"elapsed_seconds\": " + std::to_string(elapsed) + "\n}\n";
        save_report(opt.report, report);
        std::cout << report;
        return 0;
    } catch (const std::exception& error) {
        std::string report = "{\"success\":false,\"verifier\":\"verify_annotations/1.0\",\"file\":" + json_quote(current_file) +
            ",\"current_source_line\":" + std::to_string(current_line) + ",\"parts_verified\":" + std::to_string(completed_parts) +
            ",\"message\":" + json_quote(error.what()) + ",\"restore_partial\":" + (sink ? json_quote(sink->partial_path()) : "null") + "}\n";
        std::cerr << report;
        if (!opt.report.empty() && !fs::exists(opt.report)) {
            try { save_report(opt.report, report); } catch (const std::exception& ignored) { std::cerr << "Could not write failure report: " << ignored.what() << '\n'; }
        }
        return 1;
    }
}
