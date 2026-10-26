# Sums 8 words in a loop (2 elements per iteration).
# Shows basic blocks, loop-carried dependencies and branch penalties.
        ADDI R1, R0, 0        # sum   = 0
        ADDI R2, R0, 100      # base address
        ADDI R3, R0, 8        # remaining elements
loop:   LW   R4, 0(R2)
        ADD  R1, R1, R4       # load-use hazard
        LW   R5, 4(R2)
        ADD  R1, R1, R5       # load-use hazard
        ADDI R2, R2, 8
        SUBI R3, R3, 2
        BNE  R3, R0, loop
        SW   R1, 0(R0)
