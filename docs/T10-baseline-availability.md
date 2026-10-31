# T10 – Baseline Implementation Availability

## Reference Paper

**Title:** Evolutionary and Coevolutionary Multi-Agent Design Choices and Dynamics

**Authors:** Erik Hemberg, Stephen Moskal, Una-May O'Reilly, Eric Liu, and Lucille Fuller

**Venue:** GECCO '25 Companion, 2025, pp. 559–562

**DOI:** https://doi.org/10.1145/3712255.3726712

**Paper:** https://arxiv.org/abs/2507.05534

## Author Contact

An email was sent to Dr. Erik Hemberg on 1 November 2026
requesting information about the public availability of the
paper-specific Red/Blue controllers and evolutionary baselines.

**Status:** Awaiting response.

The reimplementation plan remains the fallback if the source code
is unavailable or no response is received in time.

## Objective

Verify whether the baseline implementations described in the reference paper
are publicly available and determine whether reimplementation is required.

## Findings

The paper investigates two controller representations and multiple
evolutionary approaches for cyber-agent teams:

- Finite State Machine (FSM) representations.
- Grammatical Evolution (GE) representations.
- Evolutionary algorithms, including Genetic Algorithms (GA) and
  Evolution Strategies (ES).
- An LLM-supported mutation operator for grammatical evolution.
- Evolutionary and co-evolutionary training setups.

The paper provides methodological descriptions and controller grammar
details, including material in its appendix.

The paper cites publicly available cyber-security environment resources,
including CybORG and CAGE Challenge 4. However, the paper-specific
evolutionary and co-evolutionary implementation was not located in the
public repositories and author-linked resources checked for this task.

### CAGE-4 Blue-Agent Baseline Assessment

The CAGE-4 repository provides infrastructure for implementing and
integrating custom Blue agents, including:

- `BlueFixedActionWrapper` for mapping Blue actions to fixed action indices.
- `BlueEnterpriseWrapper` for exposing observations to Blue agents.
- An example submission demonstrating the expected Blue-agent interface.
- Available actions such as Monitor, Analyse, DeployDecoy, Remove,
  Restore and BlockTraffic.

These resources provide a foundation for implementing and evaluating
custom Blue agents. However, the repository resources checked did not
identify a directly reusable specialist Blue-agent baseline matching
the requirements of this project.

Therefore, CAGE-4 will be treated as the environment and integration
framework rather than as a source of ready-made specialist Blue
baselines.

## Availability Assessment

| Component | Availability |
|---|---|
| CybORG environment | Public repository |
| CAGE Challenge 4 environment | Public repository |
| Paper-specific GA implementation | No public implementation located |
| Paper-specific ES implementation | No public implementation located |
| GE controller implementation | No public implementation located |
| LLM-supported GE mutation | No public implementation located |
| Controller grammar details | Described in the paper |
| CAGE-4 Blue-agent integration framework | Publicly available |
| Ready-made specialist Blue-agent baseline | Not identified in the resources checked |

## Conclusion

The underlying environment resources are publicly available, but a
public, directly reusable implementation of the paper's evolutionary
and co-evolutionary methods was not located during this verification.

Therefore, the project should plan to reimplement the required
paper-specific algorithms and controller representations, using the
paper as the methodological reference and the public environment
repositories as dependencies.

This is a finding from the resources checked, not proof that no
private or unindexed implementation exists.

The CAGE-4 assessment supports using its wrappers, action definitions
and example submission as implementation references. It does not
remove the need to develop our own project-specific Blue-agent
baselines.

## References

1. Hemberg et al. (2025), *Evolutionary and Coevolutionary Multi-Agent
   Design Choices and Dynamics*.
   https://doi.org/10.1145/3712255.3726712

2. arXiv preprint:
   https://arxiv.org/abs/2507.05534

3. CybORG – Cyber Operations Research Gym:
   https://github.com/cage-challenge/CybORG

4. CAGE Challenge 4:
   https://github.com/cage-challenge/cage-challenge-4