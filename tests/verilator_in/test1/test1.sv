/* used for generating test1* files. Go to verilator_in/ dir and do
$ verilator --lint-only --no-json-edit-nums --dump-tree-json test1/test1.sv && (cd obj_dir && cp Vtest1*009*.json ../test1_a.tree.json && cp Vtest1*012*.json ../test1_b.tree.json && cp Vtest1.tree.meta.json ../test1.tree.meta.json) && rm -rf obj_dir/Vtest* && rmdir obj_dir
*/

`include "test1/test1_submodule/full_adder.sv"

module serial_adder #(WIDTH=32) (
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
