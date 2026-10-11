/*
 * Plain text runner for independently computed Python secp256k1-field vectors.
 * stdin: MUL <hex> <hex> or SQR <hex> (canonical field residues)
 * stdout: one lowercase hexadecimal residue per input operation.
 */
#include "../secp256k1/Int.h"
#include <cstdlib>
#include <iostream>
#include <string>

int main() {
    Int p;
    p.SetBase16("FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2F");
    Int::SetupField(&p);
    std::string op,a,b;
    while (std::cin >> op) {
        Int x,y,z;
        if (op=="MUL") {
            if (!(std::cin >> a >> b)) return 2;
            x.SetBase16(a.c_str());
            y.SetBase16(b.c_str());
            z.ModMulK1(&x,&y);
        } else if (op=="SQR") {
            if (!(std::cin >> a)) return 2;
            x.SetBase16(a.c_str());
            z.ModSquareK1(&x);
        } else {
            std::cerr << "Unexpected operation: " << op << "\n";
            return 2;
        }
        char *value=z.GetBase16();
        if (!value) return 3;
        std::cout << value << "\n";
        free(value);
    }
    return 0;
}
