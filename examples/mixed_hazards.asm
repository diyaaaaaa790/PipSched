# Mix of RAW chains, independent work and memory ordering (store -> load).
        ADDI R1, R0, 10
        ADDI R2, R0, 20
        MUL  R3, R1, R2
        LW   R4, 0(R3)
        ADD  R5, R4, R1
        SW   R5, 4(R3)
        LW   R6, 8(R3)
        SUB  R7, R6, R2
        ADDI R8, R1, 5
        ADDI R9, R2, 7
        OR   R10, R8, R9
        SW   R10, 12(R3)
