## 2024-06-22 - Repeated Array Iteration Avoidance
**Learning:** In Python, searching the same list multiple times for different conditions (like checking if a list has 'APPROVED' and then checking if it has 'CHANGES_REQUESTED') causes repeated O(N) iterations. In this codebase's PR scheduling, checking review states multiple times caused unnecessary performance overhead.
**Action:** Always collapse multiple linear searches over the same collection into a single pass that extracts the needed state, and reuse that state in conditional checks.
