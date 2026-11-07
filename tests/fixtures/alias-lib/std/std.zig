//! Mini lib whose public decls alias a file `std` never exposes.
const hidden = @import("hidden.zig");

pub const Thing = hidden.Thing;
pub const Oops = error{Bad};
