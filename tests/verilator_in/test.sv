module serial_adder #(WIDTH) (
        input  [WIDTH-1:0] a,
        input  [WIDTH-1:0] b,
        input  cin,
        output [WIDTH-1:0] s,
        output cout);

    wire [WIDTH:0] c;

    generate for (genvar i = 0; i < WIDTH; i++)
        full_adder fa(a[i], b[i], c[i], s[i], c[i+1]);
    endgenerate

    assign c[0] = cin;
    assign cout = c[WIDTH-1];

endmodule
