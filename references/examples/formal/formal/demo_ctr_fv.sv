// demo_ctr_fv - formal wrapper for rtl/demo_ctr.v.
//
// Two things must be handled explicitly in formal that a simulation testbench
// usually hides:
//
// 1) Any-init.  `prep` runs `formalff -ff2anyinit`, so every FF without a
//    defined initial value may start with an *arbitrary* value.  A single
//    `initial assume(rst_n == 0)` only constrains time 0 and cannot clean up
//    the rest of the state; it also says nothing about when reset ends.
//    Instead, keep an explicit boot counter (initialised to 0), hold rst_n low
//    for RESET_CYCLES posedges, then require rst_n high for the rest of the
//    proof.  Holding reset across several posedges gives every DUT FF -
//    including any-init ones - a defined value before assertions are checked.
//    Do not rely on initial blocks inside the DUT: treat DUT state as
//    arbitrary at time 0 and clear it with reset.
//
// 2) Gating.  Assertions are only meaningful after reset.  Every assert (and
//    every assume about DUT state) is guarded by `boot >= RESET_CYCLES`.
//
// For a DUT with asynchronous reset, keep rst_n high after the reset window as
// this wrapper does: the posedge-sampled past_* history cannot observe a
// negedge reset that happens between clock edges.  If the DUT has only
// synchronous reset, the same boot/gating pattern applies, but clk2fflogic is
// not required in the .sby file.
module demo_ctr_fv #(
    parameter W = 8,
    parameter RESET_CYCLES = 4
) (
    input clk,
    input rst_n,
    input en,
    input [W-1:0] step
);
    localparam CNT_W = $clog2(RESET_CYCLES + 1);

    wire [W-1:0] count;
    wire         carry;

    // boot is deliberately initialised: the reset assumption below is gated
    // by it, so an arbitrary boot would leave reset unconstrained.
    reg [CNT_W-1:0] boot;
    initial boot = {CNT_W{1'b0}};

    // Previous-cycle inputs/state used by the registered-update assertion.
    reg         past_valid;
    reg         past_rst_n;
    reg         past_en;
    reg [W-1:0] past_step;
    reg [W-1:0] past_count;
    initial past_valid = 1'b0;
    initial past_rst_n = 1'b0;
    initial past_en = 1'b0;
    initial past_step = {W{1'b0}};
    initial past_count = {W{1'b0}};

    demo_ctr #(.W(W)) dut (
        .clk(clk),
        .rst_n(rst_n),
        .en(en),
        .step(step),
        .count(count),
        .carry(carry)
    );

    always @(posedge clk) begin
        if (boot != RESET_CYCLES) begin
            boot <= boot + 1'b1;
        end
        else;  // hold at RESET_CYCLES
    end

    // Reset discipline: assume, not assert.  While boot is low the environment
    // must hold rst_n low; afterwards rst_n must stay high.  This is an
    // always @(*) constraint applied on every formal step, so it covers the
    // arbitrary initial state instead of only the first time step.
    always @(*) begin
        if (boot < RESET_CYCLES) begin
            assume(rst_n == 1'b0);
        end
        else begin
            assume(rst_n == 1'b1);
        end
    end

    // Registered behaviour, compared against the previous cycle.  past_valid
    // skips the first comparison, when no meaningful history exists yet.
    always @(posedge clk) begin
        past_valid <= 1'b1;
        past_rst_n <= rst_n;
        past_en    <= en;
        past_step  <= step;
        past_count <= count;
        if (past_valid) begin
            if (past_rst_n == 1'b0) begin
                assert(count == {W{1'b0}});
            end
            else if (past_en) begin
                assert(count == past_count + past_step);
            end
            else begin
                assert(count == past_count);
            end
        end
        else;  // no history yet
    end

    // carry is combinational; check it only after reset has finished.
    always @(*) begin
        if (boot >= RESET_CYCLES) begin
            assert(carry == (&count));
        end
        else;  // reset not finished
    end
endmodule
