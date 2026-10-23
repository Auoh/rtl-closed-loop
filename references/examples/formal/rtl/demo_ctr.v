// demo_ctr - minimal DUT used by the formal templates in this directory.
// Async active-low reset; count increments by `step` when `en` is high.
module demo_ctr #(
    parameter W = 8
) (
    input  wire         clk,
    input  wire         rst_n,
    input  wire         en,
    input  wire [W-1:0] step,
    output reg  [W-1:0] count,
    output wire         carry
);
    assign carry = &count;

    always @(posedge clk or negedge rst_n) begin
        if (rst_n == 1'b0) begin
            count <= {W{1'b0}};
        end
        else if (en) begin
            count <= count + step;
        end
        else begin
            count <= count;
        end
    end
endmodule
