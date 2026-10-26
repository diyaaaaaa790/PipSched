# A conditional skip: three basic blocks, optimizer works inside each block.
        LW   R1, 0(R2)
        ADD  R3, R1, R1
        LW   R4, 4(R2)
        SUB  R5, R4, R3
        BEQ  R5, R0, done
        LW   R6, 8(R2)
        ADD  R7, R6, R5
        LW   R8, 12(R2)
        OR   R9, R8, R7
        SW   R9, 16(R2)
done:   SW   R5, 20(R2)
