// pulse_stretch - single-cycle request stretched into a fixed-length busy
// pulse.  `done` is combinational and high on the last busy cycle.
module pulse_stretch #(
    parameter LATENCY = 3
) (
    input       clk,
    input       rst_n,
    input       req,
    output reg  busy,
    output wire done
);
    localparam CNT_W = $clog2(LATENCY + 1);

    reg [CNT_W-1:0] cnt;

    assign done = busy && (cnt == LATENCY - 1);

    always @(posedge clk or negedge rst_n) begin
        if (rst_n == 1'b0) begin
            busy <= 1'b0;
        end
        else if (req && !busy) begin
            busy <= 1'b1;
        end
        else if (busy && (cnt == LATENCY - 1)) begin
            busy <= 1'b0;
        end
        else begin
            busy <= busy;
        end
    end

    always @(posedge clk or negedge rst_n) begin
        if (rst_n == 1'b0) begin
            cnt <= {CNT_W{1'b0}};
        end
        else if (!busy) begin
            cnt <= {CNT_W{1'b0}};
        end
        else if (cnt != LATENCY - 1) begin
            cnt <= cnt + 1'b1;
        end
        else begin
            cnt <= cnt;
        end
    end
endmodule
