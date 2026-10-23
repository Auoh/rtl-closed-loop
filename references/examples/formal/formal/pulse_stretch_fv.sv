// pulse_stretch_fv - shadow-counter checks for a multi-cycle protocol.
//
// The DUT turns a one-cycle `req` into a busy pulse of exactly LATENCY cycles,
// with `done` high on the last busy cycle.  A second counter (`shadow`) is
// maintained in the wrapper, independent of the DUT's internal counter.  The
// assertions compare edge-by-edge behaviour against this shadow state, which
// catches:
//   - busy starting without a request,
//   - busy dropping early (short pulse),
//   - done at the wrong bit/cycle boundary,
//   - a request during busy extending or restarting the pulse.
//
// Reset handling is the same as demo_ctr_fv: `prep` runs
// `formalff -ff2anyinit`, so hold rst_n low for RESET_CYCLES after an explicit
// boot counter, then keep it high.  Assertions are gated by boot.
module pulse_stretch_fv #(
    parameter LATENCY = 3,
    parameter RESET_CYCLES = 4
) (
    input clk,
    input rst_n,
    input req
);
    localparam CNT_W = $clog2(LATENCY + 1);
    // The boot counter must be able to hold RESET_CYCLES itself; using CNT_W
    // here would silently cap it (e.g. 2 bits for LATENCY=3) and make every
    // assertion gate permanently false.
    localparam BOOT_W = $clog2(RESET_CYCLES + 1);

    wire busy;
    wire done;

    reg [CNT_W-1:0] shadow;
    reg [BOOT_W-1:0] boot;
    initial begin
        shadow = {CNT_W{1'b0}};
        boot = {BOOT_W{1'b0}};
    end

    reg         past_valid;
    reg         past_req;
    reg         past_busy;
    reg         past_done;
    reg [CNT_W-1:0] past_shadow;
    initial begin
        past_valid = 1'b0;
        past_req = 1'b0;
        past_busy = 1'b0;
        past_done = 1'b0;
        past_shadow = {CNT_W{1'b0}};
    end

    pulse_stretch #(.LATENCY(LATENCY)) dut (
        .clk(clk),
        .rst_n(rst_n),
        .req(req),
        .busy(busy),
        .done(done)
    );

    always @(posedge clk) begin
        if (boot != RESET_CYCLES) begin
            boot <= boot + 1'b1;
        end
        else;  // hold
    end

    // Same reset discipline as the base template: assume reset for the first
    // RESET_CYCLES, then keep it deasserted (async-reset edges between clocks
    // cannot be tracked by posedge history).
    always @(*) begin
        if (boot < RESET_CYCLES) begin
            assume(rst_n == 1'b0);
        end
        else begin
            assume(rst_n == 1'b1);
        end
    end

    // Shadow counter: number of elapsed busy cycles, 0-based.  It is reset by
    // the same reset the DUT uses, so any-init state cannot leak in.
    always @(posedge clk or negedge rst_n) begin
        if (rst_n == 1'b0) begin
            shadow <= {CNT_W{1'b0}};
        end
        else if (!busy) begin
            shadow <= {CNT_W{1'b0}};
        end
        else if (shadow != LATENCY - 1) begin
            shadow <= shadow + 1'b1;
        end
        else begin
            shadow <= shadow;
        end
    end

    // Previous-cycle history, also reset asynchronously so it is defined from
    // the first post-reset comparison.
    always @(posedge clk or negedge rst_n) begin
        if (rst_n == 1'b0) begin
            past_valid <= 1'b0;
            past_req <= 1'b0;
            past_busy <= 1'b0;
            past_done <= 1'b0;
            past_shadow <= {CNT_W{1'b0}};
        end
        else begin
            past_valid <= 1'b1;
            past_req <= req;
            past_busy <= busy;
            past_done <= done;
            past_shadow <= shadow;
        end
    end

    // Cyclic properties: compare this edge with the previous edge.
    always @(posedge clk) begin
        if (past_valid && (boot >= RESET_CYCLES)) begin
            // Start condition: busy may only rise after a request.
            if (!past_busy && busy) begin
                assert(past_req);
            end
            else;  // hold
            // No early release: busy must stay high until the shadow counter
            // reaches the final cycle.  This uses the independent shadow
            // state, not the DUT's own `done`, so a DUT that releases early
            // (and raises done early with it) is still caught.
            if (past_busy && (past_shadow != LATENCY - 1)) begin
                assert(busy);
            end
            else;  // hold
            // Release exactly at the boundary: one cycle after the final busy
            // cycle, busy must be low.
            if (past_busy && (past_shadow == LATENCY - 1)) begin
                assert(!busy);
            end
            else;  // hold
            // Shadow counter advances exactly once per busy cycle.
            if (past_busy && busy) begin
                if (past_shadow != LATENCY - 1) begin
                    assert(shadow == past_shadow + 1'b1);
                end
                else begin
                    assert(shadow == past_shadow);
                end
            end
            else;  // hold
            if (!past_busy) begin
                assert(shadow == {CNT_W{1'b0}});
            end
            else;  // hold
        end
        else;  // reset window
    end

    // Combinational protocol invariants after reset.
    always @(*) begin
        if (boot >= RESET_CYCLES) begin
            // done is high exactly on the last busy cycle.
            assert(done == (busy && (shadow == LATENCY - 1)));
            // The shadow counter never passes the final cycle.
            assert(shadow <= LATENCY - 1);
        end
        else;  // reset window
    end
endmodule
