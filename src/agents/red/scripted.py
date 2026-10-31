"""Scripted Red strategies built on CAGE-4's FiniteStateRedAgent (T19).

CAGE-4's Red keeps a state per host (K known, S services scanned, U user shell, R root; a trailing D means a decoy was
seen there) and picks its next action from a probability table per state. A variant only overrides two things:
the table (`state_transitions_probability`) and how hosts of each state are prioritised. Column order of every row:

    [DiscoverRemoteSystems, AggressiveServiceDiscovery, StealthServiceDiscovery, DiscoverDeception,
     ExploitRemoteService, PrivilegeEscalate, Impact, DegradeServices, Withdraw]

None = the action is not offered in that state. Only real CAGE-4 Red actions are used, so every action is legal by
construction (D3). Three variants are for training sparring; ONE is held out for the generalisation test (T44) and must
not be used while tuning or training Blue (see HELD_OUT).
"""
from __future__ import annotations

from CybORG.Agents.SimpleAgents.FiniteStateRedAgent import FiniteStateRedAgent


class _Variant(FiniteStateRedAgent):
    PRIORITISE_SERVERS = False

    def __init__(self, name=None, np_random=None, agent_subnets=None):
        super().__init__(name=name, np_random=np_random, agent_subnets=agent_subnets)
        self.prioritise_servers = self.PRIORITISE_SERVERS


class AggressiveRed(_Variant):
    """Fast and loud: only the noisy 75%-flagged scan, goes straight for exploit, root, then Impact/Degrade."""

    PRIORITISE_SERVERS = True

    def set_host_state_priority_list(self):
        # push hosts forward: prefer hosts that already have a shell
        return {"K": 10, "KD": 10, "S": 15, "SD": 15, "U": 20, "UD": 20, "R": 5, "RD": 5}

    def state_transitions_probability(self):
        return {
            "K":  [0.1,  0.9,  None, None, None, None, None, None, None],
            "KD": [None, 1.0,  None, None, None, None, None, None, None],
            "S":  [0.1,  None, None, None, 0.9,  None, None, None, None],
            "SD": [None, None, None, None, 1.0,  None, None, None, None],
            "U":  [0.1,  None, None, None, None, 0.9,  None, None, None],
            "UD": [None, None, None, None, None, 1.0,  None, None, None],
            "R":  [0.05, None, None, None, None, None, 0.65, 0.3,  None],
            "RD": [None, None, None, None, None, None, 0.65, 0.35, None],
        }


class StealthyRed(_Variant):
    """Slow and quiet: only the 25%-flagged scan, spends most time discovering, strikes rarely."""

    def set_host_state_priority_list(self):
        # keep exploring; touch rooted hosts sparingly
        return {"K": 25, "KD": 25, "S": 20, "SD": 20, "U": 5, "UD": 5, "R": 0, "RD": 0}

    def state_transitions_probability(self):
        return {
            "K":  [0.3,  None, 0.7,  None, None, None, None, None, None],
            "KD": [None, None, 1.0,  None, None, None, None, None, None],
            "S":  [0.4,  None, None, 0.1,  0.5,  None, None, None, None],
            "SD": [None, None, None, 0.1,  0.9,  None, None, None, None],
            "U":  [0.5,  None, None, None, None, 0.5,  None, None, None],
            "UD": [None, None, None, None, None, 1.0,  None, None, None],
            "R":  [0.7,  None, None, None, None, None, 0.15, 0.15, None],
            "RD": [None, None, None, None, None, None, 0.5,  0.5,  None],
        }


class DeceptionAwareRed(_Variant):
    """Probes for decoys before exploiting; once a decoy is seen it avoids that service (FSM already excludes its PID)."""

    PRIORITISE_SERVERS = True

    def set_host_state_priority_list(self):
        return {"K": 15, "KD": 15, "S": 30, "SD": 10, "U": 10, "UD": 5, "R": 10, "RD": 5}

    def state_transitions_probability(self):
        return {
            "K":  [0.3,  0.1,  0.6,  None, None, None, None, None, None],
            "KD": [None, 0.2,  0.8,  None, None, None, None, None, None],
            "S":  [0.1,  None, None, 0.6,  0.3,  None, None, None, None],
            "SD": [None, None, None, 0.1,  0.9,  None, None, None, None],
            "U":  [0.3,  None, None, None, None, 0.7,  None, None, None],
            "UD": [None, None, None, None, None, 1.0,  None, None, None],
            "R":  [0.3,  None, None, None, None, None, 0.4,  0.3,  None],
            "RD": [None, None, None, None, None, None, 0.5,  0.5,  None],
        }


class HitAndRunRed(_Variant):
    """HELD OUT. Mixes both scans, hits servers, then Withdraws from hosts so Blue's Remove/Restore find nothing.

    Withdraw removes ALL of this agent's sessions on a host. On its only shell host that would strand the agent for the
    rest of the episode (it would just Sleep), so Withdraw is offered only while it holds shells on 2+ hosts.
    """

    PRIORITISE_SERVERS = True
    WITHDRAW_COL = 8
    SHELL_STATES = ("U", "UD", "R", "RD")

    def __init__(self, name=None, np_random=None, agent_subnets=None):
        super().__init__(name=name, np_random=np_random, agent_subnets=agent_subnets)
        self._with_withdraw = self.state_transitions_probability  # the dict the base class stored in __init__
        self._without_withdraw = self._drop_withdraw(self._with_withdraw)

    @classmethod
    def _drop_withdraw(cls, table):
        """Same table with Withdraw removed and each row renormalised to sum to 1."""
        out = {}
        for state, row in table.items():
            row = list(row)
            row[cls.WITHDRAW_COL] = None
            total = sum(v for v in row if v is not None)
            out[state] = [None if v is None else v / total for v in row]
        return out

    def get_action(self, observation, action_space):
        shells = sum(1 for h in self.host_states.values() if h["state"] in self.SHELL_STATES)
        self.state_transitions_probability = self._with_withdraw if shells >= 2 else self._without_withdraw
        return super().get_action(observation, action_space)

    def set_host_state_priority_list(self):
        return {"K": 10, "KD": 10, "S": 15, "SD": 15, "U": 20, "UD": 10, "R": 15, "RD": 5}

    def state_transitions_probability(self):
        return {
            "K":  [0.2,  0.4,  0.4,  None, None, None, None, None, None],
            "KD": [None, 0.5,  0.5,  None, None, None, None, None, None],
            "S":  [0.1,  None, None, 0.1,  0.8,  None, None, None, None],
            "SD": [None, None, None, 0.1,  0.9,  None, None, None, None],
            "U":  [0.1,  None, None, None, None, 0.7,  None, None, 0.2],
            "UD": [None, None, None, None, None, 0.8,  None, None, 0.2],
            "R":  [0.1,  None, None, None, None, None, 0.5,  0.1,  0.3],
            "RD": [None, None, None, None, None, None, 0.5,  0.1,  0.4],
        }


# name -> class. BASELINE is CAGE-4's own default red; TRAINING may be used to train and tune; HELD_OUT only for T44.
BASELINE = {"cage4_default": FiniteStateRedAgent}
TRAINING = {"aggressive": AggressiveRed, "stealthy": StealthyRed, "deception_aware": DeceptionAwareRed}
HELD_OUT = {"hit_and_run": HitAndRunRed}
ALL = {**BASELINE, **TRAINING, **HELD_OUT}
