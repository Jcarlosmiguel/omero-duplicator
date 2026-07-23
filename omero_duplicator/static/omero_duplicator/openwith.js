//
// Copyright (c) 2026 Joao Miguel.
//
// This program is free software: you can redistribute it and/or modify
// it under the terms of the GNU Affero General Public License as
// published by the Free Software Foundation, either version 3 of the
// License, or (at your option) any later version.
//
// This program is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
// GNU Affero General Public License for more details.
//
// You should have received a copy of the GNU Affero General Public License
// along with this program.  If not, see <http://www.gnu.org/licenses/>.
//

// Registers the Duplicator as an "Open with..." option in the webclient
// tree, so selecting a Project/Dataset/Image (or several) and choosing
// Duplicator pre-fills the Type and ID field(s) instead of a blank form.
OME.setOpenWithUrlProvider("omero_duplicator", function(selected, url) {
    if (!selected || selected.length === 0) {
        return url;
    }
    var type = selected[0].type;
    var objType = type.charAt(0).toUpperCase() + type.slice(1);
    var ids = selected.map(function(s) { return s.id; }).join(',');
    return url + "?obj_type=" + objType + "&obj_id=" + ids;
});
