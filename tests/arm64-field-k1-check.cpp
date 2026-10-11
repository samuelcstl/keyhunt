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
        if (op=="MUL" || op=="MULI" || op=="MULA" || op=="MULB") {
            if (!(std::cin >> a >> b)) return 2;
            x.SetBase16(a.c_str());
            y.SetBase16(b.c_str());
            if (op=="MUL") {
                z.ModMulK1(&x,&y);
            } else if (op=="MULI") {
                z.Set(&x);
                z.ModMulK1(&y);  // Hot in-place overload.
            } else if (op=="MULA") {
                z.Set(&x);
                z.ModMulK1(&z,&y); // 2-argument overload, out aliases a.
            } else {
                z.Set(&y);
                z.ModMulK1(&x,&z); // 2-argument overload, out aliases b.
            }
        } else if (op=="SQR" || op=="SQRA") {
            if (!(std::cin >> a)) return 2;
            x.SetBase16(a.c_str());
            if (op=="SQRA") {
                z.Set(&x);
                z.ModSquareK1(&z); // Output aliases input.
            } else {
                z.ModSquareK1(&x);
            }
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
