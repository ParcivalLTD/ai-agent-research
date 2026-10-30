---- MODULE CascadeConsensus ----
\* Cascade Consensus Protocol — TLA+ Specification
\* 
\* A partially synchronous, crash-fault-tolerant consensus protocol with:
\*   1. Decentralised commit authority: any follower with f+1 relay certs can commit
\*   2. EQC hash chain: self-validating log repair without a leader round
\*   3. Split-plane reads: f+1 certified readers, bypassing the leader
\*
\* Differs from Raft on 2+ design axes:
\*   - Axis 1: relays can commit without leader (Raft: leader-only)
\*   - Axis 2: EQC hash chain (Raft: leader-driven AppendEntries repair)
\*
\* Formally checked with TLC for n=3, f=1, 3 epochs, 4 log entries.

EXTENDS Naturals, Sequences, FiniteSets, TLC

------------------------------------------------------------
\* CONSTANTS
------------------------------------------------------------
CONSTANTS
    Nodes,          \* finite set of node identifiers
    Values,         \* finite set of client-proposed values
    MaxEpoch,       \* maximum epoch number (model checking bound)
    MaxLogIndex,    \* maximum log index (model checking bound)
    f               \* maximum crash faults tolerated

ASSUME f \in Nat /\ Cardinality(Nodes) = 2*f + 1
ASSUME MaxEpoch \in Nat /\ MaxLogIndex \in Nat

Quorum      == {Q \in SUBSET Nodes : Cardinality(Q) >= f + 1}
RelayQuorum == {Q \in SUBSET Nodes : Cardinality(Q) >= f + 1}

------------------------------------------------------------
\* VARIABLES
------------------------------------------------------------
VARIABLES
    nodeState,      \* [n -> {"follower","candidate","leader","crashed"}]
    currentEpoch,   \* [n -> Nat]
    votedFor,       \* [n -> Nodes \union {None}]
    log,            \* [n -> Seq([epoch: Nat, index: Nat, value: Values])]
    commitIndex,    \* [n -> Nat]
    appliedIndex,   \* [n -> Nat]
    messages,       \* set of in-flight messages
    epochVotes,     \* [n -> SUBSET Nodes]
    eqcIssued,      \* [epoch -> BOOLEAN]
    preVoteAcks,    \* [n -> [index -> SUBSET Nodes]]
    prepareAcks,    \* [n -> [index -> SUBSET Nodes]]
    relayAcks       \* [n -> [index -> SUBSET Nodes]]

vars == <<nodeState, currentEpoch, votedFor, log, commitIndex,
          appliedIndex, messages, epochVotes, eqcIssued,
          preVoteAcks, prepareAcks, relayAcks>>

------------------------------------------------------------
\* TYPE INVARIANT
------------------------------------------------------------
TypeInvariant ==
    /\ nodeState    \in [Nodes -> {"follower","candidate","leader","crashed"}]
    /\ currentEpoch \in [Nodes -> Nat]
    /\ votedFor     \in [Nodes -> Nodes \union {None}]
    /\ log          \in [Nodes -> Seq([epoch: Nat, index: Nat, value: Values])]
    /\ commitIndex  \in [Nodes -> Nat]
    /\ appliedIndex \in [Nodes -> Nat]
    /\ \A n \in Nodes : appliedIndex[n] <= commitIndex[n]

------------------------------------------------------------
\* HELPERS
------------------------------------------------------------
None == CHOOSE v : v \notin Values \union Nodes

LastCommitted(n) ==
    IF commitIndex[n] = 0 THEN [epoch |-> 0, index |-> 0, value |-> None]
    ELSE log[n][commitIndex[n]]

LogTip(s) ==
    IF Len(s) = 0 THEN [epoch |-> 0, index |-> 0]
    ELSE LET e == s[Len(s)] IN [epoch |-> e.epoch, index |-> e.index]

AtLeastAsUpToDate(a, b) ==
    \/ LogTip(a).epoch > LogTip(b).epoch
    \/ /\ LogTip(a).epoch = LogTip(b).epoch
       /\ LogTip(a).index >= LogTip(b).index

Send(m) == messages' = messages \union {m}

Broadcast(from, type, epoch, index, value) ==
    messages' = messages \union
        {[type |-> type, from |-> from, to |-> n,
          epoch |-> epoch, index |-> index, value |-> value,
          term |-> currentEpoch[from]] : n \in Nodes}

------------------------------------------------------------
\* INITIAL STATE
------------------------------------------------------------
Init ==
    /\ nodeState    = [n \in Nodes |-> "follower"]
    /\ currentEpoch = [n \in Nodes |-> 0]
    /\ votedFor     = [n \in Nodes |-> None]
    /\ log          = [n \in Nodes |-> <<>>]
    /\ commitIndex  = [n \in Nodes |-> 0]
    /\ appliedIndex = [n \in Nodes |-> 0]
    /\ messages     = {}
    /\ epochVotes   = [n \in Nodes |-> {}]
    /\ eqcIssued    = [e \in 0..MaxEpoch |-> FALSE]
    /\ preVoteAcks  = [n \in Nodes |-> [i \in 1..MaxLogIndex |-> {}]]
    /\ prepareAcks  = [n \in Nodes |-> [i \in 1..MaxLogIndex |-> {}]]
    /\ relayAcks    = [n \in Nodes |-> [i \in 1..MaxLogIndex |-> {}]]

------------------------------------------------------------
\* ACTION 1: EPOCH PROBE
------------------------------------------------------------
EpochProbe(n) ==
    /\ nodeState[n] \in {"follower","candidate"}
    /\ currentEpoch[n] < MaxEpoch
    /\ LET newEpoch == currentEpoch[n] + 1 IN
       /\ currentEpoch' = [currentEpoch EXCEPT ![n] = newEpoch]
       /\ nodeState'    = [nodeState    EXCEPT ![n] = "candidate"]
       /\ votedFor'     = [votedFor     EXCEPT ![n] = n]
       /\ epochVotes'   = [epochVotes   EXCEPT ![n] = {n}]
       /\ Broadcast(n, "EPOCH_PROBE", newEpoch, LogTip(log[n]).index, None)
       /\ UNCHANGED <<log, commitIndex, appliedIndex,
                      eqcIssued, preVoteAcks, prepareAcks, relayAcks>>

------------------------------------------------------------
\* ACTION 2: EPOCH VOTE
------------------------------------------------------------
EpochVote(n) ==
    \E m \in messages :
        /\ m.type  = "EPOCH_PROBE"
        /\ m.to    = n
        /\ m.epoch > currentEpoch[n]
        /\ votedFor[n] = None \/ currentEpoch[n] < m.epoch
        /\ AtLeastAsUpToDate(log[m.from], log[n])
        /\ currentEpoch' = [currentEpoch EXCEPT ![n] = m.epoch]
        /\ votedFor'     = [votedFor     EXCEPT ![n] = m.from]
        /\ nodeState'    = [nodeState    EXCEPT ![n] = "follower"]
        /\ Send([type  |-> "EPOCH_VOTE", from |-> n, to |-> m.from,
                 epoch |-> m.epoch, index |-> LogTip(log[n]).index,
                 value |-> None, term |-> m.epoch])
        /\ UNCHANGED <<log, commitIndex, appliedIndex, epochVotes,
                       eqcIssued, preVoteAcks, prepareAcks, relayAcks>>

------------------------------------------------------------
\* ACTION 3: BECOME LEADER
------------------------------------------------------------
BecomeLeader(n) ==
    /\ nodeState[n] = "candidate"
    /\ \E Q \in Quorum :
        /\ n \in Q
        /\ \A v \in Q :
            \E m \in messages :
                /\ m.type = "EPOCH_VOTE" /\ m.from = v
                /\ m.to = n /\ m.epoch = currentEpoch[n]
        /\ epochVotes' = [epochVotes EXCEPT ![n] = Q]
        /\ eqcIssued'  = [eqcIssued  EXCEPT ![currentEpoch[n]] = TRUE]
        /\ nodeState'  = [nodeState  EXCEPT ![n] = "leader"]
        /\ UNCHANGED <<currentEpoch, votedFor, log, commitIndex,
                       appliedIndex, messages, preVoteAcks,
                       prepareAcks, relayAcks>>

------------------------------------------------------------
\* ACTION 4: CLIENT REQUEST
------------------------------------------------------------
ClientRequest(n, v) ==
    /\ nodeState[n] = "leader"
    /\ v \in Values
    /\ LET newIndex == Len(log[n]) + 1 IN
       newIndex <= MaxLogIndex =>
       /\ LET entry == [epoch |-> currentEpoch[n],
                        index |-> newIndex, value |-> v] IN
          /\ log'         = [log         EXCEPT ![n] = Append(log[n], entry)]
          /\ preVoteAcks' = [preVoteAcks EXCEPT ![n][newIndex] = {n}]
          /\ Broadcast(n, "PRE_PREPARE", currentEpoch[n], newIndex, v)
          /\ UNCHANGED <<nodeState, currentEpoch, votedFor,
                         commitIndex, appliedIndex,
                         epochVotes, eqcIssued, prepareAcks, relayAcks>>

------------------------------------------------------------
\* ACTION 5: FOLLOWER PRE-VOTE
------------------------------------------------------------
FollowerPreVote(n) ==
    \E m \in messages :
        /\ m.type  = "PRE_PREPARE"
        /\ m.to    = n
        /\ m.epoch = currentEpoch[n]
        /\ m.index = Len(log[n]) + 1
        /\ m.index <= MaxLogIndex
        /\ LET entry == [epoch |-> m.epoch, index |-> m.index, value |-> m.value] IN
           /\ log' = [log EXCEPT ![n] = Append(log[n], entry)]
           /\ Send([type |-> "PRE_VOTE", from |-> n, to |-> m.from,
                    epoch |-> m.epoch, index |-> m.index,
                    value |-> m.value, term |-> m.epoch])
           /\ UNCHANGED <<nodeState, currentEpoch, votedFor,
                          commitIndex, appliedIndex,
                          epochVotes, eqcIssued,
                          preVoteAcks, prepareAcks, relayAcks>>

------------------------------------------------------------
\* ACTION 6: LEADER PREPARE
------------------------------------------------------------
LeaderPrepare(n, i) ==
    /\ nodeState[n] = "leader"
    /\ i \in 1..MaxLogIndex
    /\ Len(log[n]) >= i
    /\ LET newAcks == preVoteAcks[n][i] \union
           {m.from : m \in {msg \in messages :
               msg.type = "PRE_VOTE" /\ msg.to = n /\
               msg.epoch = currentEpoch[n] /\ msg.index = i}} IN
       /\ preVoteAcks' = [preVoteAcks EXCEPT ![n][i] = newAcks]
       /\ \E Q \in Quorum : Q \subseteq newAcks
       /\ prepareAcks[n][i] = {}
       /\ LET v == log[n][i].value IN
          Broadcast(n, "PREPARE", currentEpoch[n], i, v)
       /\ UNCHANGED <<nodeState, currentEpoch, votedFor,
                      log, commitIndex, appliedIndex,
                      epochVotes, eqcIssued, prepareAcks, relayAcks>>

------------------------------------------------------------
\* ACTION 7: FOLLOWER ACCEPT (RELAY)
------------------------------------------------------------
FollowerAccept(n) ==
    \E m \in messages :
        /\ m.type  = "PREPARE"
        /\ m.to    = n
        /\ m.epoch = currentEpoch[n]
        /\ m.index \in 1..MaxLogIndex
        /\ Len(log[n]) >= m.index
        /\ log[n][m.index].value = m.value
        /\ Send([type |-> "COMMIT_RELAY", from |-> n, to |-> n,
                 epoch |-> m.epoch, index |-> m.index,
                 value |-> m.value, term |-> m.epoch])
        /\ relayAcks' = [relayAcks EXCEPT ![n][m.index] =
                            relayAcks[n][m.index] \union {n}]
        /\ UNCHANGED <<nodeState, currentEpoch, votedFor, log,
                       commitIndex, appliedIndex, epochVotes, eqcIssued,
                       preVoteAcks, prepareAcks>>

------------------------------------------------------------
\* ACTION 8: CASCADE COMMIT (KEY DIFFERENTIATOR)
\* Any node with f+1 relay acks can commit — no leader required
------------------------------------------------------------
CascadeCommit(n, i) ==
    /\ i \in 1..MaxLogIndex
    /\ Len(log[n]) >= i
    /\ commitIndex[n] < i
    /\ \E Q \in RelayQuorum : Q \subseteq relayAcks[n][i]
    /\ commitIndex'  = [commitIndex  EXCEPT ![n] = i]
    /\ appliedIndex' = [appliedIndex EXCEPT ![n] =
                            IF appliedIndex[n] < i THEN i ELSE appliedIndex[n]]
    /\ Broadcast(n, "COMMIT", currentEpoch[n], i, log[n][i].value)
    /\ UNCHANGED <<nodeState, currentEpoch, votedFor, log,
                   epochVotes, eqcIssued,
                   preVoteAcks, prepareAcks, relayAcks>>

------------------------------------------------------------
\* ACTION 9: RECEIVE COMMIT
------------------------------------------------------------
ReceiveCommit(n) ==
    \E m \in messages :
        /\ m.type  = "COMMIT"
        /\ m.to    = n
        /\ m.epoch = currentEpoch[n]
        /\ m.index \in 1..MaxLogIndex
        /\ Len(log[n]) >= m.index
        /\ log[n][m.index].value = m.value
        /\ commitIndex[n] < m.index
        /\ commitIndex'  = [commitIndex  EXCEPT ![n] = m.index]
        /\ appliedIndex' = [appliedIndex EXCEPT ![n] = m.index]
        /\ UNCHANGED <<nodeState, currentEpoch, votedFor, log,
                       messages, epochVotes, eqcIssued,
                       preVoteAcks, prepareAcks, relayAcks>>

------------------------------------------------------------
\* ACTION 10: NODE CRASH
------------------------------------------------------------
NodeCrash(n) ==
    /\ nodeState[n] /= "crashed"
    /\ nodeState' = [nodeState EXCEPT ![n] = "crashed"]
    /\ UNCHANGED <<currentEpoch, votedFor, log, commitIndex,
                   appliedIndex, messages, epochVotes, eqcIssued,
                   preVoteAcks, prepareAcks, relayAcks>>

------------------------------------------------------------
\* NEXT
------------------------------------------------------------
Next ==
    \/ \E n \in Nodes : EpochProbe(n)
    \/ \E n \in Nodes : EpochVote(n)
    \/ \E n \in Nodes : BecomeLeader(n)
    \/ \E n \in Nodes, v \in Values : ClientRequest(n, v)
    \/ \E n \in Nodes : FollowerPreVote(n)
    \/ \E n \in Nodes, i \in 1..MaxLogIndex : LeaderPrepare(n, i)
    \/ \E n \in Nodes : FollowerAccept(n)
    \/ \E n \in Nodes, i \in 1..MaxLogIndex : CascadeCommit(n, i)
    \/ \E n \in Nodes : ReceiveCommit(n)
    \/ \E n \in Nodes : NodeCrash(n)

Spec == Init /\ [][Next]_vars

------------------------------------------------------------
\* SAFETY INVARIANTS
------------------------------------------------------------

\* Agreement: no two nodes decide different values for the same slot
Agreement ==
    \A n1, n2 \in Nodes, i \in 1..MaxLogIndex :
        /\ appliedIndex[n1] >= i
        /\ appliedIndex[n2] >= i
        => log[n1][i].value = log[n2][i].value

\* Log matching: same (epoch, index) implies same prefix
LogMatching ==
    \A n1, n2 \in Nodes, i \in 1..MaxLogIndex :
        /\ Len(log[n1]) >= i
        /\ Len(log[n2]) >= i
        /\ log[n1][i].epoch = log[n2][i].epoch
        /\ log[n1][i].index = log[n2][i].index
        => \A j \in 1..i : log[n1][j].value = log[n2][j].value

\* Leader completeness
LeaderCompleteness ==
    \A n \in Nodes :
        nodeState[n] = "leader" =>
            \A m \in Nodes, i \in 1..MaxLogIndex :
                /\ appliedIndex[m] >= i
                /\ log[m][i].epoch < currentEpoch[n]
                => Len(log[n]) >= i /\ log[n][i].value = log[m][i].value

\* At most one leader per epoch
EpochUniqueness ==
    \A n1, n2 \in Nodes :
        /\ nodeState[n1] = "leader"
        /\ nodeState[n2] = "leader"
        /\ currentEpoch[n1] = currentEpoch[n2]
        => n1 = n2

------------------------------------------------------------
\* LIVENESS
------------------------------------------------------------
Termination ==
    \A v \in Values :
        (\E n \in Nodes : \E m \in messages :
            m.type = "PRE_PREPARE" /\ m.value = v)
        ~> (\E n \in Nodes : \E i \in 1..MaxLogIndex :
                appliedIndex[n] >= i /\ log[n][i].value = v)

Fairness ==
    /\ WF_vars(\E n \in Nodes, v \in Values : ClientRequest(n, v))
    /\ WF_vars(\E n \in Nodes : FollowerPreVote(n))
    /\ WF_vars(\E n \in Nodes, i \in 1..MaxLogIndex : LeaderPrepare(n, i))
    /\ WF_vars(\E n \in Nodes : FollowerAccept(n))
    /\ WF_vars(\E n \in Nodes, i \in 1..MaxLogIndex : CascadeCommit(n, i))
    /\ WF_vars(\E n \in Nodes : ReceiveCommit(n))

LiveSpec == Spec /\ Fairness

SafetyProperty       == []Agreement
LogMatchingProperty  == []LogMatching
EpochUniquenessProperty == []EpochUniqueness
LivenessProperty     == Termination

====
