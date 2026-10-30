--------------------------- MODULE Raft ----------------------------
(*
 * Raft consensus algorithm — TLA+ specification
 *
 * Based on: Ongaro & Ousterhout, "In Search of an Understandable
 * Consensus Algorithm" (USENIX ATC 2014)
 *
 * This spec models the core Raft safety properties:
 *   1. Election Safety: at most one leader per term
 *   2. Log Matching: if two logs agree on index+term, they agree on all
 *      earlier entries
 *   3. Leader Completeness: if an entry is committed in term T, it is
 *      present in all leaders of term > T
 *   4. State Machine Safety: all servers apply the same sequence of entries
 *)

EXTENDS Naturals, Sequences, FiniteSets, TLC

CONSTANTS
    Servers,          \* set of server IDs
    MaxTerm,          \* bound on election terms (for finite-state model checking)
    MaxLogLen         \* bound on log length

ASSUME IsFiniteSet(Servers)
ASSUME MaxTerm \in Nat /\ MaxTerm > 0
ASSUME MaxLogLen \in Nat /\ MaxLogLen > 0

--------------------------------------------------------------------
\* Roles

Follower  == "follower"
Candidate == "candidate"
Leader    == "leader"

Roles == {Follower, Candidate, Leader}

--------------------------------------------------------------------
\* Log entries

VARIABLES
    currentTerm,   \* currentTerm[s] : term server s has seen
    votedFor,      \* votedFor[s]    : candidate s voted for in current term (or Nil)
    log,           \* log[s]         : sequence of <<term, value>> pairs
    commitIndex,   \* commitIndex[s] : highest log index known to be committed
    role,          \* role[s]        : Follower | Candidate | Leader
    votes,         \* votes[s]       : set of servers that voted for s in current term
    nextIndex,     \* nextIndex[s][f]: next log index to send to follower f (leader state)
    matchIndex     \* matchIndex[s][f]: highest index known to be replicated on f

Nil == 0

vars == <<currentTerm, votedFor, log, commitIndex, role, votes, nextIndex, matchIndex>>

--------------------------------------------------------------------
\* Helper operators

Quorum == {Q \in SUBSET Servers : Cardinality(Q) * 2 > Cardinality(Servers)}

IsQuorum(Q) == Q \in Quorum

LastTerm(s) ==
    IF Len(log[s]) = 0 THEN 0
    ELSE log[s][Len(log[s])].term

UpToDate(s, t) ==
    \* s's log is at least as up-to-date as t's log
    \/ LastTerm(s) > LastTerm(t)
    \/ /\ LastTerm(s) = LastTerm(t)
       /\ Len(log[s]) >= Len(log[t])

LogsMatch(s, t, idx) ==
    \* Logs agree on all entries up to index idx
    /\ Len(log[s]) >= idx
    /\ Len(log[t]) >= idx
    /\ \A i \in 1..idx : log[s][i] = log[t][i]

Committed(s, idx) ==
    \* Entry idx is committed if a quorum has replicated it in the same term
    /\ idx > 0
    /\ idx <= commitIndex[s]

--------------------------------------------------------------------
\* Initial state

Init ==
    /\ currentTerm = [s \in Servers |-> 1]
    /\ votedFor    = [s \in Servers |-> Nil]
    /\ log         = [s \in Servers |-> <<>>]
    /\ commitIndex = [s \in Servers |-> 0]
    /\ role        = [s \in Servers |-> Follower]
    /\ votes       = [s \in Servers |-> {}]
    /\ nextIndex   = [s \in Servers |-> [f \in Servers |-> 1]]
    /\ matchIndex  = [s \in Servers |-> [f \in Servers |-> 0]]

--------------------------------------------------------------------
\* Actions

\* RequestVote: candidate s asks server t for its vote
RequestVote(s, t) ==
    /\ role[s] = Candidate
    /\ t /= s
    /\ currentTerm[t] <= currentTerm[s]
    /\ (votedFor[t] = Nil \/ votedFor[t] = s)
    /\ UpToDate(s, t)
    /\ votes' = [votes EXCEPT ![s] = votes[s] \cup {t}]
    /\ votedFor' = [votedFor EXCEPT ![t] = s]
    /\ UNCHANGED <<currentTerm, log, commitIndex, role, nextIndex, matchIndex>>

\* BecomeLeader: candidate s wins election
BecomeLeader(s) ==
    /\ role[s] = Candidate
    /\ IsQuorum(votes[s] \cup {s})
    /\ role' = [role EXCEPT ![s] = Leader]
    /\ nextIndex'  = [nextIndex  EXCEPT ![s] = [f \in Servers |-> Len(log[s]) + 1]]
    /\ matchIndex' = [matchIndex EXCEPT ![s] = [f \in Servers |-> 0]]
    /\ UNCHANGED <<currentTerm, votedFor, log, commitIndex, votes>>

\* StartElection: follower s times out and starts election
StartElection(s) ==
    /\ role[s] = Follower
    /\ currentTerm[s] < MaxTerm
    /\ currentTerm' = [currentTerm EXCEPT ![s] = currentTerm[s] + 1]
    /\ role'        = [role        EXCEPT ![s] = Candidate]
    /\ votes'       = [votes       EXCEPT ![s] = {}]
    /\ votedFor'    = [votedFor    EXCEPT ![s] = s]
    /\ UNCHANGED <<log, commitIndex, nextIndex, matchIndex>>

\* AppendEntry: leader s appends a new entry to its own log
AppendEntry(s) ==
    /\ role[s] = Leader
    /\ Len(log[s]) < MaxLogLen
    /\ LET entry == [term |-> currentTerm[s], value |-> Len(log[s]) + 1]
       IN log' = [log EXCEPT ![s] = Append(log[s], entry)]
    /\ UNCHANGED <<currentTerm, votedFor, commitIndex, role, votes, nextIndex, matchIndex>>

\* ReplicateEntry: leader s sends entry idx to follower t
ReplicateEntry(s, t) ==
    /\ role[s] = Leader
    /\ t /= s
    /\ nextIndex[s][t] <= Len(log[s])
    /\ LET idx == nextIndex[s][t]
           entry == log[s][idx]
       IN
       /\ \/ /\ Len(log[t]) >= idx - 1
             /\ \/ idx = 1
                \/ log[t][idx-1] = log[s][idx-1]   \* Prev log consistency
             /\ log'        = [log        EXCEPT ![t] = Append(SubSeq(log[t], 1, idx-1), entry)]
             /\ matchIndex' = [matchIndex EXCEPT ![s][t] = idx]
             /\ nextIndex'  = [nextIndex  EXCEPT ![s][t] = idx + 1]
          \/ /\ nextIndex'  = [nextIndex  EXCEPT ![s][t] = MAX(nextIndex[s][t] - 1, 1)]
             /\ UNCHANGED <<log, matchIndex>>
    /\ UNCHANGED <<currentTerm, votedFor, commitIndex, role, votes>>

\* AdvanceCommit: leader s advances its commitIndex
AdvanceCommit(s) ==
    /\ role[s] = Leader
    /\ \E idx \in (commitIndex[s]+1)..Len(log[s]) :
        /\ log[s][idx].term = currentTerm[s]
        /\ IsQuorum({t \in Servers : matchIndex[s][t] >= idx} \cup {s})
        /\ commitIndex' = [commitIndex EXCEPT ![s] = idx]
    /\ UNCHANGED <<currentTerm, votedFor, log, role, votes, nextIndex, matchIndex>>

\* LearnCommit: follower t learns of committed entries from leader s
LearnCommit(s, t) ==
    /\ role[s] = Leader
    /\ commitIndex[s] > commitIndex[t]
    /\ commitIndex' = [commitIndex EXCEPT ![t] = MIN(commitIndex[s], Len(log[t]))]
    /\ UNCHANGED <<currentTerm, votedFor, log, role, votes, nextIndex, matchIndex>>

--------------------------------------------------------------------
\* Next

Next ==
    \/ \E s \in Servers : StartElection(s)
    \/ \E s, t \in Servers : RequestVote(s, t)
    \/ \E s \in Servers : BecomeLeader(s)
    \/ \E s \in Servers : AppendEntry(s)
    \/ \E s, t \in Servers : ReplicateEntry(s, t)
    \/ \E s \in Servers : AdvanceCommit(s)
    \/ \E s, t \in Servers : LearnCommit(s, t)

Spec == Init /\ [][Next]_vars /\ WF_vars(Next)

--------------------------------------------------------------------
\* Safety invariants

ElectionSafety ==
    \A s, t \in Servers :
        (role[s] = Leader /\ role[t] = Leader /\ s /= t)
        => currentTerm[s] /= currentTerm[t]

LogMatchingInv ==
    \A s, t \in Servers :
    \A i \in 1..MIN(Len(log[s]), Len(log[t])) :
        log[s][i].term = log[t][i].term
        => LogsMatch(s, t, i)

LeaderCompletenessInv ==
    \A s \in Servers :
    \A t \in Servers :
        /\ role[s] = Leader
        /\ commitIndex[t] > 0
        /\ Committed(t, commitIndex[t])
        => /\ Len(log[s]) >= commitIndex[t]
           /\ log[s][commitIndex[t]] = log[t][commitIndex[t]]

StateMachineSafety ==
    \A s, t \in Servers :
    \A i \in 1..MIN(commitIndex[s], commitIndex[t]) :
        log[s][i] = log[t][i]

--------------------------------------------------------------------
\* Liveness

SomeLeaderElected ==
    <>(\E s \in Servers : role[s] = Leader)

====================================================================
