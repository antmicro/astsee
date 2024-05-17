/* used for generating test1* files. Go to verilator_in/ dir and do
$ verilator --lint-only --no-json-edit-nums --dump-tree-json -Mdir test1_obj_dir test1/test1.sv && (cd test1_obj_dir && ls -Q *.tree.json | grep -xv '"Vtest1_\(001\|006\|007\|009\|012\)_.*\.tree\.json"' | xargs rm)
(we remove majority of .tree.json to avoid bloating repo)*/

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
