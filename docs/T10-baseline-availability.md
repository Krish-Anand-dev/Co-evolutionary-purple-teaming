# T10 – Baseline Implementation Availability

## Reference Paper

**Title:** Evolutionary and Coevolutionary Multi-Agent Design Choices and Dynamics

**Authors:** Erik Hemberg, Stephen Moskal, Una-May O'Reilly, Eric Liu, and Lucille Fuller

**Venue:** GECCO '25 Companion, 2025, pp. 559–562

**DOI:** https://doi.org/10.1145/3712255.3726712

**Paper:** https://arxiv.org/abs/2507.05534

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