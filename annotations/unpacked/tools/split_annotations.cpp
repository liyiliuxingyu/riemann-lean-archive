#include <openssl/evp.h>
#include <zstd.h>

#include <algorithm>
#include <charconv>
#include <cerrno>
#include <cstdio>
#include <cstring>
#include <filesystem>
#include <fcntl.h>
#include <iomanip>
#include <iostream>
#include <limits>
#include <memory>
#include <sstream>
#include <stdexcept>
#include <string>
#include <string_view>
#include <unistd.h>
#include <vector>

namespace fs = std::filesystem;
using U64 = std::uint64_t;
constexpr std::size_t IO_BYTES = 4 * 1024 * 1024;
constexpr std::size_t HASH_BUFFER_BYTES = 8 * 1024 * 1024;
constexpr U64 GITHUB_LIMIT = 100ULL * 1024 * 1024;

class Sha256 {
    EVP_MD_CTX* context_ = EVP_MD_CTX_new();
    bool finalized_ = false;
public:
    Sha256() {
        if (!context_ || EVP_DigestInit_ex(context_, EVP_sha256(), nullptr) != 1)
            throw std::runtime_error("Cannot initialize SHA-256");
    }
    ~Sha256() { EVP_MD_CTX_free(context_); }
    Sha256(const Sha256&) = delete;
    Sha256& operator=(const Sha256&) = delete;
    void append(const void* data, std::size_t size) {
        if (finalized_) throw std::runtime_error("SHA-256 already finalized");
        if (size && EVP_DigestUpdate(context_, data, size) != 1)
            throw std::runtime_error("Cannot update SHA-256");
    }
    std::string finish() {
        if (finalized_) throw std::runtime_error("SHA-256 already finalized");
        unsigned char digest[EVP_MAX_MD_SIZE];
        unsigned int length = 0;
        if (EVP_DigestFinal_ex(context_, digest, &length) != 1 || length != 32)
            throw std::runtime_error("Cannot finish SHA-256");
        finalized_ = true;
        const char* hex = "0123456789abcdef";
        std::string result(64, '0');
        for (unsigned int i = 0; i < length; ++i) {
            result[2 * i] = hex[digest[i] >> 4];
            result[2 * i + 1] = hex[digest[i] & 15];
        }
        return result;
    }
};

U64 number(std::string_view value, const char* name) {
    U64 n = 0;
    auto parsed = std::from_chars(value.data(), value.data() + value.size(), n);
    if (value.empty() || parsed.ec != std::errc() || parsed.ptr != value.data() + value.size())
        throw std::runtime_error(std::string("Invalid integer for ") + name);
    return n;
}

struct Options {
    fs::path source, out;
    U64 first = 0, last = 0, max_bytes = 0;
    bool allow_final_no_lf = false;
};

Options options(int argc, char** argv) {
    Options result;
    for (int i = 1; i < argc; ++i) {
        std::string key = argv[i];
        if (key == "--allow-final-no-lf") { result.allow_final_no_lf = true; continue; }
        if (i + 1 >= argc) throw std::runtime_error("Option lacks a value: " + key);
        std::string value = argv[++i];
        if (key == "--source") result.source = value;
        else if (key == "--out") result.out = value;
        else if (key == "--first") result.first = number(value, "first");
        else if (key == "--last") result.last = number(value, "last");
        else if (key == "--max-bytes") result.max_bytes = number(value, "max-bytes");
        else throw std::runtime_error("Unknown option: " + key);
    }
    if (result.source.empty() || result.out.empty() || !result.first || result.last < result.first ||
        result.last == std::numeric_limits<U64>::max() || !result.max_bytes || result.max_bytes >= GITHUB_LIMIT)
        throw std::runtime_error("Require source/out, 1 <= first <= last, and 1 <= max-bytes < 100 MiB");
    if (!fs::is_regular_file(result.source)) throw std::runtime_error("Source is not a regular file");
    if (!fs::is_directory(result.out)) throw std::runtime_error("Output directory must already exist");
    return result;
}

inline bool json_space(unsigned char c) { return c == ' ' || c == '\t' || c == '\r'; }

class Splitter {
    const Options& opt_;
    Sha256 annotated_hash_, original_hash_;
    std::string original_buffer_, chunk_, pair_;
    bool annotation_ = true;
    std::size_t line_start_ = 0;
    U64 next_line_, chunk_first_ = 0, chunk_last_ = 0, chunk_records_ = 0;
    U64 records_ = 0, annotated_bytes_ = 0, original_bytes_ = 0, chunks_ = 0, max_pair_ = 0;
    bool last_original_has_lf_ = true;

    void check_annotation(std::string_view line) {
        constexpr std::string_view prefix = "-- @line ";
        if (line.size() <= prefix.size() || line.substr(0, prefix.size()) != prefix)
            throw std::runtime_error("Bad annotation prefix at original line " + std::to_string(next_line_));
        const char* p = line.data() + prefix.size();
        const char* end = line.data() + line.size();
        if (*p < '1' || *p > '9') throw std::runtime_error("Noncanonical annotation line number");
        U64 actual = 0;
        auto parsed = std::from_chars(p, end, actual);
        if (parsed.ec != std::errc() || parsed.ptr == end || *parsed.ptr != ' ')
            throw std::runtime_error("Malformed annotation line number or separator");
        if (actual != next_line_ || actual > opt_.last)
            throw std::runtime_error("Nonconsecutive or out-of-range annotation line number: expected " + std::to_string(next_line_));
        p = parsed.ptr + 1;
        while (p < end && json_space(static_cast<unsigned char>(*p))) ++p;
        if (p == end) throw std::runtime_error("Empty annotation text");
    }

    void check_original(std::string_view line) {
        const char* p = line.data();
        const char* end = p + line.size();
        while (p < end && json_space(static_cast<unsigned char>(*p))) ++p;
        while (end > p && json_space(static_cast<unsigned char>(end[-1]))) --end;
        if (end - p < 2 || *p != '{' || end[-1] != '}')
            throw std::runtime_error("Original line lacks JSON object boundaries at line " + std::to_string(next_line_));
    }

    void append_original(std::string_view raw) {
        original_bytes_ += raw.size();
        // Hash reasonably large blocks rather than calling OpenSSL for each source record.
        if (raw.size() >= HASH_BUFFER_BYTES) {
            if (!original_buffer_.empty()) {
                original_hash_.append(original_buffer_.data(), original_buffer_.size());
                original_buffer_.clear();
            }
            original_hash_.append(raw.data(), raw.size());
            return;
        }
        original_buffer_.append(raw.data(), raw.size());
        if (original_buffer_.size() >= HASH_BUFFER_BYTES) {
            original_hash_.append(original_buffer_.data(), original_buffer_.size());
            original_buffer_.clear();
        }
    }

    void publish_chunk() {
        if (chunk_.empty()) return;
        std::ostringstream label;
        label << "chunk" << std::setfill('0') << std::setw(4) << (chunks_ + 1) << ".txt";
        const std::string name = label.str();
        const fs::path path = opt_.out / name;
        Sha256 hash;
        hash.append(chunk_.data(), chunk_.size());
        const std::string digest = hash.finish();
        const int fd = ::open(path.c_str(), O_CREAT | O_EXCL | O_WRONLY | O_NOFOLLOW, 0644);
        if (fd == -1) throw std::runtime_error("Cannot create chunk without overwriting: " + std::string(std::strerror(errno)));
        std::size_t position = 0;
        while (position < chunk_.size()) {
            const ssize_t n = ::write(fd, chunk_.data() + position, chunk_.size() - position);
            if (n == -1 && errno == EINTR) continue;
            if (n <= 0) {
                const std::string error = std::strerror(errno);
                ::close(fd);
                throw std::runtime_error("Chunk write failed: " + error);
            }
            position += static_cast<std::size_t>(n);
        }
        if (::close(fd) != 0) throw std::runtime_error("Chunk close failed");
        ++chunks_;
        std::cout << "{\"type\":\"chunk\",\"file\":\"" << name
            << "\",\"bytes\":" << chunk_.size() << ",\"sha256\":\"" << digest
            << "\",\"first_line\":" << chunk_first_ << ",\"last_line\":" << chunk_last_
            << ",\"records\":" << chunk_records_ << "}\n" << std::flush;
        if (!std::cout) throw std::runtime_error("Cannot report completed chunk");
        std::string ack;
        if (!std::getline(std::cin, ack) || ack != "ok")
            throw std::runtime_error("Parent did not acknowledge chunk with exactly ok");
        if (fs::exists(path)) throw std::runtime_error("Acknowledged chunk still exists; parent must import and remove it first");
        chunk_.clear();
        chunk_records_ = 0;
    }

    void complete_pair(bool lf) {
        const std::size_t n = pair_.size();
        if (n > opt_.max_bytes) throw std::runtime_error("A complete record pair exceeds max-bytes");
        if (!chunk_.empty() && n > opt_.max_bytes - chunk_.size()) publish_chunk();
        if (chunk_.empty()) chunk_first_ = next_line_;
        chunk_.append(pair_);
        chunk_last_ = next_line_;
        ++chunk_records_;
        ++records_;
        ++next_line_;
        max_pair_ = std::max<U64>(max_pair_, n);
        last_original_has_lf_ = lf;
        pair_.clear();
        line_start_ = 0;
        annotation_ = true;
    }

    void finish_line(bool lf) {
        const std::size_t length = pair_.size() - line_start_ - (lf ? 1 : 0);
        const std::string_view line(pair_.data() + line_start_, length);
        if (annotation_) {
            if (!lf) throw std::runtime_error("Unterminated annotation without its original row");
            check_annotation(line);
            annotation_ = false;
            line_start_ = pair_.size();
        } else {
            check_original(line);
            append_original(std::string_view(pair_.data() + line_start_, pair_.size() - line_start_));
            complete_pair(lf);
        }
    }

public:
    explicit Splitter(const Options& opt) : opt_(opt), next_line_(opt.first) {
        chunk_.reserve(static_cast<std::size_t>(opt.max_bytes));
        original_buffer_.reserve(HASH_BUFFER_BYTES + 1024 * 1024);
        pair_.reserve(4096);
    }
    void feed(const char* data, std::size_t size) {
        annotated_hash_.append(data, size);
        annotated_bytes_ += size;
        const char* p = data;
        const char* end = data + size;
        while (p < end) {
            const char* nl = static_cast<const char*>(std::memchr(p, '\n', static_cast<std::size_t>(end - p)));
            const std::size_t n = nl ? static_cast<std::size_t>(nl - p + 1) : static_cast<std::size_t>(end - p);
            if (pair_.size() > opt_.max_bytes || n > opt_.max_bytes - pair_.size())
                throw std::runtime_error("A record pair exceeds max-bytes near original line " + std::to_string(next_line_));
            pair_.append(p, n);
            if (nl) finish_line(true);
            p += n;
        }
    }
    void finish(U64 compressed_bytes, U64 frames) {
        if (!pair_.empty()) {
            if (annotation_) throw std::runtime_error("Unterminated annotation without its original row");
            if (line_start_ == pair_.size()) throw std::runtime_error("Annotation is missing its original row");
            if (!opt_.allow_final_no_lf) throw std::runtime_error("Original row lacks final LF in a non-final volume");
            finish_line(false);
        }
        if (!annotation_) throw std::runtime_error("Annotation is missing its original row");
        if (records_ != opt_.last - opt_.first + 1 || next_line_ != opt_.last + 1)
            throw std::runtime_error("Expected source record range does not match decompressed input");
        if (!original_buffer_.empty()) original_hash_.append(original_buffer_.data(), original_buffer_.size());
        original_buffer_.clear();
        const std::string original_sha = original_hash_.finish();
        const std::string annotated_sha = annotated_hash_.finish();
        publish_chunk();
        std::cout << "{\"type\":\"complete\",\"first_line\":" << opt_.first
            << ",\"last_line\":" << opt_.last << ",\"records\":" << records_
            << ",\"chunks\":" << chunks_ << ",\"annotated_bytes\":" << annotated_bytes_
            << ",\"annotated_sha256\":\"" << annotated_sha << "\",\"original_bytes\":" << original_bytes_
            << ",\"original_sha256\":\"" << original_sha << "\",\"maximum_record_pair_bytes\":" << max_pair_
            << ",\"compressed_bytes_read\":" << compressed_bytes << ",\"zstd_frames\":" << frames
            << ",\"last_original_has_lf\":" << (last_original_has_lf_ ? "true" : "false") << "}\n" << std::flush;
        if (!std::cout) throw std::runtime_error("Cannot report completion");
    }
};

int main(int argc, char** argv) {
    try {
        const Options opt = options(argc, argv);
        Splitter splitter(opt);
        using File = std::unique_ptr<FILE, int(*)(FILE*)>;
        File source(std::fopen(opt.source.c_str(), "rb"), std::fclose);
        if (!source) throw std::runtime_error("Cannot open compressed source");
        std::unique_ptr<ZSTD_DCtx, decltype(&ZSTD_freeDCtx)> decoder(ZSTD_createDCtx(), ZSTD_freeDCtx);
        if (!decoder) throw std::runtime_error("Cannot initialize Zstandard decoder");
        std::vector<char> input(IO_BYTES), output(IO_BYTES);
        U64 compressed = 0, frames = 0;
        std::size_t last_result = 1;
        for (;;) {
            const std::size_t size = std::fread(input.data(), 1, input.size(), source.get());
            if (!size) {
                if (std::ferror(source.get())) throw std::runtime_error("Compressed input read failed");
                break;
            }
            compressed += size;
            ZSTD_inBuffer in{input.data(), size, 0};
            bool drain = false;
            do {
                const std::size_t before = in.pos;
                ZSTD_outBuffer out{output.data(), output.size(), 0};
                last_result = ZSTD_decompressStream(decoder.get(), &out, &in);
                if (ZSTD_isError(last_result))
                    throw std::runtime_error(std::string("Zstandard decompression failed: ") + ZSTD_getErrorName(last_result));
                if (out.pos) splitter.feed(output.data(), out.pos);
                if (!last_result) ++frames;
                drain = out.pos == out.size && last_result != 0;
                if (in.pos == before && !out.pos) {
                    if (in.pos < in.size) throw std::runtime_error("Zstandard made no progress");
                    drain = false;
                }
            } while (in.pos < in.size || drain);
        }
        if (last_result || !frames) throw std::runtime_error("Truncated or empty Zstandard source");
        splitter.finish(compressed, frames);
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "split_annotations: " << error.what() << '\n';
        return 1;
    }
}
