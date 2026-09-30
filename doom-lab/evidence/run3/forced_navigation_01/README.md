# Forced-recursion navigation development, four reused seeds

Both candidates omit direct current-pixel and direct action-history policy connections, under the frozen brain implementation `d91ec34d`. They were tested on the same four reused navigation development seeds 1220000000–1220000003. This was a bounded diagnostic, not confirmation.

The scale0.3 candidate b106afac won 0/4: four native timeouts at 2,100 tics, mean native return -0.21. Every one of its 2,100 qualified actions was turn_left. The scale1 candidate fc409482 won 1/4, with the other three episodes stopped at the explicit 120-second wall limit. All its 1,532 queries qualified; its executed actions were forward894, turn_left88, turn_right549 and use1. A wall cutoff is neither a native timeout nor a completed evaluation. Its mean partial return/time are not comparable estimates of completed episode outcomes.

The entire wave took 121.12 seconds with at most eight workers. The full-completion verifier correctly failed because three scheduled native episodes were incomplete; their traces and outcomes remain in the denominator. No retries or replacements were used. The separate all-attempt trace check also includes their partial native accounting.

This supports a concrete failure diagnosis: the smaller-scale forced-recursion policy spins indefinitely; the larger-scale policy sometimes navigates but remains unreliable and slower. More internal dependency alone did not solve exploration or credit assignment. A visible novelty diagnostic must explicitly measure rewards for rotation rather than assume pixel novelty means useful travel.

Full AWS evidence: `/home/ec2-user/doom-v3-20260929/runs/forced_navigation_01` (3,142,367 bytes before extra verification). Compact summaries and verification receipts remain locally.
