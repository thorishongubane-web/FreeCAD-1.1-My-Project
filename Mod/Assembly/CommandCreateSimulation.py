# SPDX-License-Identifier: LGPL-2.1-or-later
# /**************************************************************************
#                                                                           *
#    Copyright (c) 2024 Ondsel <development@ondsel.com>                     *
#                                                                           *
#    This file is part of FreeCAD.                                          *
#                                                                           *
#    FreeCAD is free software: you can redistribute it and/or modify it     *
#    under the terms of the GNU Lesser General Public License as            *
#    published by the Free Software Foundation, either version 2.1 of the   *
#    License, or (at your option) any later version.                        *
#                                                                           *
#    FreeCAD is distributed in the hope that it will be useful, but         *
#    WITHOUT ANY WARRANTY; without even the implied warranty of             *
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU       *
#    Lesser General Public License for more details.                        *
#                                                                           *
#    You should have received a copy of the GNU Lesser General Public       *
#    License along with FreeCAD. If not, see                                *
#    <https://www.gnu.org/licenses/>.                                       *
#                                                                           *
# **************************************************************************/

import configparser
import glob
import math
import re
import os
import time
import importFCMat
import Materials
import FreeCAD as App

from pivy import coin
from Part import LineSegment, Compound

from PySide.QtCore import QT_TRANSLATE_NOOP

if App.GuiUp:
    import FreeCADGui as Gui
    from PySide import QtCore, QtGui, QtWidgets
    from PySide.QtWidgets import (
        QPushButton,
        QMenu,
        QDialog,
        QComboBox,
        QLineEdit,
        QGridLayout,
        QLabel,
        QDialogButtonBox,
    )
    from PySide.QtCore import Qt, QPoint
    from PySide.QtGui import QCursor, QIcon, QGuiApplication

import UtilsAssembly
import Preferences

translate = App.Qt.translate


# ============================================================
# PENDULUM / DAP3D HELPERS
#   Pure-Python maths + FreeCAD unit handling.
#   FreeCAD works in mm, DAP3D and the dynamics below work in SI (m, kg, s).
# ============================================================

GRAVITY_MAGNITUDE = 9.81                 # m/s^2, fixed (not user-editable)
GRAVITY_VECTOR = [0.0, 0.0, -GRAVITY_MAGNITUDE]  # default direction; the user picks it in Step 6

# Gravity direction choices shown in Step 6 (unit directions, global axes)
GRAVITY_PRESETS = [
    ("−Z  (down, FreeCAD default)", (0.0, 0.0, -1.0)),
    ("+Z", (0.0, 0.0, 1.0)),
    ("−Y", (0.0, -1.0, 0.0)),
    ("+Y", (0.0, 1.0, 0.0)),
    ("−X", (-1.0, 0.0, 0.0)),
    ("+X", (1.0, 0.0, 0.0)),
    ("Custom…", None),
]

MAX_SIM_FRAMES = 200000  # upper limit on reported time steps per run


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def _rodrigues(v, u, th):
    """Rotate vector v about unit axis u by angle th (rad)."""
    c, s = math.cos(th), math.sin(th)
    uxv = _cross(u, v)
    uv = _dot(u, v)
    return [v[i] * c + uxv[i] * s + u[i] * uv * (1.0 - c) for i in range(3)]


def _rot_matrix(rot):
    """3x3 list-matrix of an App.Rotation."""
    m = rot.toMatrix()
    return [[getattr(m, f"A{i + 1}{k + 1}") for k in range(3)] for i in range(3)]


def _mat_T_vec(A, v):
    """A^T v"""
    return [sum(A[k][i] * v[k] for k in range(3)) for i in range(3)]


def _AT_J_A(A, J):
    """A^T J A  (global inertia tensor -> body-frame inertia tensor)"""
    return [
        [sum(A[k][i] * J[k][l] * A[l][j] for k in range(3) for l in range(3)) for j in range(3)]
        for i in range(3)
    ]


def _inv3(M):
    """Inverse of a 3x3 list-matrix."""
    a, b, c = M[0]; d, e, f = M[1]; g, h, i = M[2]
    det = a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)
    if abs(det) < 1e-300:
        raise ValueError("singular inertia matrix")
    return [[(e * i - f * h) / det, (c * h - b * i) / det, (b * f - c * e) / det],
            [(f * g - d * i) / det, (a * i - c * g) / det, (c * d - a * f) / det],
            [(d * h - e * g) / det, (b * g - a * h) / det, (a * e - b * d) / det]]


def _A_from_p(p):
    """DAP3D rotation matrix from Euler parameters p = [e0, e1, e2, e3]."""
    e0, e = p[0], p[1:]
    et = [[0.0, -e[2], e[1]], [e[2], 0.0, -e[0]], [-e[1], e[0], 0.0]]
    return [[(2 * e0 * e0 - 1) * (i == j) + 2 * (e[i] * e[j] + e0 * et[i][j])
             for j in range(3)] for i in range(3)]


def _mvec(v):
    return "[" + "; ".join(f"{x:.10g}" for x in v) + "]"


def _mmat(M):
    return "[" + "\n            ".join(" ".join(f"{x:.10g}" for x in row) for row in M) + "]"


def _to_kg_m3(value):
    """Density given as Quantity / string / number -> float in kg/m^3."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        q = value if hasattr(value, "getValueAs") else App.Units.Quantity(str(value))
        res = q.getValueAs("kg/m^3")
        return float(getattr(res, "Value", res))
    except Exception:
        try:
            return float(str(value).split()[0])  # plain number -> assume kg/m^3
        except Exception:
            return None


MATLAB_RESULTS_SCRIPT = r"""% dap3d_pendulum_results.m   (written by FreeCAD with the DAP3D model)
% Run AFTER dap, in the same MATLAB session:
%     >> dap                       (model folder: __MODEL__)
%     >> dap3d_pendulum_results
%
% Turns DAP3D's solution (T, uT) into the same quantities FreeCAD exports,
% shows them, and saves __MODEL___DAP3D_results.xlsx with the same columns
% as FreeCAD's results workbook.

if ~exist('uT', 'var') || ~exist('T', 'var')
    error('No DAP3D results (T, uT). Run dap first, using model folder "__MODEL__".');
end

freecad_pendulum_info;               % pendulum properties exported by FreeCAD -> struct "pend"

%% ---- Accelerations from DAP3D's post-processor -------------------------
try
    post;                                            % fills rdd, wd (nt x nB x 3)
    dap_acom = reshape(rdd(:,1,:), [], 3);           % COM acceleration, body 1
    dap_wdot = reshape(wd(:,1,:),  [], 3);           % angular acceleration, body 1
    accSource = 'DAP3D post.m';
catch err
    warning('post.m failed (%s). Using numerical derivatives of the velocities.', err.message);
    nB_ = size(uT, 2) / 13;
    dap_acom = [gradient(uT(:,7*nB_+1), T) gradient(uT(:,7*nB_+2), T) gradient(uT(:,7*nB_+3), T)];
    dap_wdot = [gradient(uT(:,7*nB_+4), T) gradient(uT(:,7*nB_+5), T) gradient(uT(:,7*nB_+6), T)];
    accSource = 'numerical derivative of DAP3D velocities';
end

%% ---- Same quantities as the FreeCAD CSV --------------------------------
nt  = numel(T);
nB_ = size(uT, 2) / 13;                 % 13 numbers per body; pendulum = body 1
m   = pend.mass;
g   = pend.gravity(:)';
P   = pend.pivot(:)';
u   = pend.axis(:)' / norm(pend.axis);
d0  = pend.com_cad(:)' - P;             % pivot -> COM in the CAD pose (theta = 0)

dap_com  = uT(:, 1:3);                  % r of body 1
dap_p    = uT(:, 4:7);                  % Euler parameters of body 1
dap_vcom = uT(:, 7*nB_ + (1:3));        % r_dot
dap_w    = uT(:, 7*nB_ + (4:6));        % omega (global)

% Swing angle measured from the VERTICAL (hanging position), about the joint
% axis, as in FreeCAD. "Vertical" = gravity projected into the swing plane.
% Components ALONG the axis are removed first: an offset along the hinge
% (e.g. joint on the end face of a pin) would otherwise distort the angle.
d   = dap_com - P;
gv  = g - dot(g, u) * u;   gv = gv / norm(gv);       % straight down in the swing plane
dpp = d - (d * u') * u;
dap_theta = unwrap(atan2(cross(repmat(gv, nt, 1), dpp, 2) * u', dpp * gv')) * 180/pi;
dap_theta = dap_theta + 360 * round((pend.theta0_deg - dap_theta(1)) / 360);

dap_omega = dap_w * u';                 % angular velocity about the joint axis
dap_alpha = dap_wdot * u';              % angular acceleration about the joint axis

% ---- Force drivers: applied force, torque about the axis, potential energy
%      (same definitions as FreeCAD; potentials are zero when hanging)
if ~isfield(pend, 'torque'),    pend.torque = 0;    end
if ~isfield(pend, 'force_on'),  pend.force_on = 0;  end
if ~isfield(pend, 'forces_desc'), pend.forces_desc = 'None'; end
th_rad  = dap_theta * pi/180;           % angle from the vertical
F_app   = zeros(nt, 3);                 % sum of applied forces (N)
tau_app = zeros(nt, 1);                 % their torque about the joint axis (N m)
V_app   = zeros(nt, 1);                 % potential energy of the conservative parts (J)
if pend.torque ~= 0                     % 'n': constant moment about the axis
    tau_app = tau_app + pend.torque;
    V_app   = V_app - pend.torque * th_rad;
end
for k = 1:nt
    if pend.force_on                    % 'f': fixed in space, at the COM
        Fk = pend.force(:)';
        F_app(k,:) = F_app(k,:) + Fk;
        tau_app(k) = tau_app(k) + cross(d(k,:), Fk) * u';
        V_app(k)   = V_app(k) - Fk * d(k,:)';           % like gravity
    end
end

dap_R    = m * dap_acom - m * repmat(g, nt, 1) - F_app;   % pivot force: m a = R + m g + F_app
dap_Rmag = sqrt(sum(dap_R.^2, 2));

% Energies: KE = 1/2 m v.v + 1/2 w' J w,  PE = -m g.d  (zero at pivot height)
dap_KE = zeros(nt, 1);
for k = 1:nt
    e0 = dap_p(k,1);  e = dap_p(k,2:4)';
    et = [0 -e(3) e(2); e(3) 0 -e(1); -e(2) e(1) 0];
    A  = (2*e0^2 - 1) * eye(3) + 2 * (e*e' + e0*et);
    J  = A * pend.Jp * A';
    dap_KE(k) = 0.5 * m * (dap_vcom(k,:) * dap_vcom(k,:)') + 0.5 * dap_w(k,:) * J * dap_w(k,:)';
end
dap_PE = -m * (d * g') + V_app;          % gravity + force drivers
dap_E  = dap_KE + dap_PE;

dap_results = [T dap_theta dap_omega dap_alpha dap_com dap_vcom dap_acom ...
               dap_R dap_Rmag dap_KE dap_PE dap_E];

%% ---- Summary -----------------------------------------------------------
% Period from the turning points: omega changes sign at every end of the
% swing, i.e. twice per period. Two sign changes (about one full swing) are
% enough; the start (released from rest, omega = 0) is not counted.
i0 = find(dap_omega(1:end-1) .* dap_omega(2:end) < 0);
if numel(i0) >= 2
    tz = T(i0) - dap_omega(i0) .* (T(i0+1) - T(i0)) ./ (dap_omega(i0+1) - dap_omega(i0));
    dap_period = 2 * mean(diff(tz));
else
    dap_period = NaN;
end
fprintf('\n=====  DAP3D PENDULUM RESULTS (%s)  =====\n', pend.body);
fprintf('Reporting steps  : %d (0 to %g s)\n', nt, T(end));
if isnan(dap_period)
    fprintf(['Period           : not measured - the run has %d turning point(s), ' ...
             'at least 2 are needed.\n                   Simulate longer (Final time), ' ...
             'or check that the pendulum swings freely.\n'], numel(i0));
else
    fprintf('Period           : %.5f s (from %d turning points)\n', dap_period, numel(i0));
end
fprintf('Max |omega|      : %.5f rad/s\n', max(abs(dap_omega)));
fprintf('Max pivot force  : %.5f N\n', max(dap_Rmag));
fprintf('Energy drift     : %.3e J\n', max(dap_E) - min(dap_E));
fprintf('Accelerations    : %s\n', accSource);

%% ---- Plots -------------------------------------------------------------
figure('Name', 'DAP3D pendulum results', 'Color', 'w');
subplot(3,1,1); plot(T, dap_theta); grid on; xlabel('t (s)'); ylabel('\theta (deg)'); title('Swing angle')
subplot(3,1,2); plot(T, dap_omega); grid on; xlabel('t (s)'); ylabel('\omega (rad/s)'); title('Angular velocity')
subplot(3,1,3); plot(T, dap_alpha); grid on; xlabel('t (s)'); ylabel('\alpha (rad/s^2)'); title('Angular acceleration')

%% ---- Excel workbook: every value in its own cell -----------------------
% Opens correctly in Excel whatever the computer's regional settings.
xlsFile = '__MODEL___DAP3D_results.xlsx';
try
    hdr = {'t [s]','theta [deg]','omega [rad/s]','alpha [rad/s^2]', ...
           'COM x [m]','COM y [m]','COM z [m]','COM vx [m/s]','COM vy [m/s]','COM vz [m/s]', ...
           'COM ax [m/s^2]','COM ay [m/s^2]','COM az [m/s^2]', ...
           'Rx [N]','Ry [N]','Rz [N]','|R| [N]','KE [J]','PE [J]','E total [J]'};
    c = pend.com_cad;  pv = pend.pivot;  ax = pend.axis;  gr = pend.gravity;
    props = {'Parameter','Value / x','y','z','Unit';
             'Solver','DAP3D (MATLAB ode45 standard method)',[],[],'';
             'Body', pend.body, [],[],'';
             'Joint type', 'Revolute', [],[],'';
             'Density', pend.density, [],[], 'kg/m^3';
             'Mass', m, [],[], 'kg';
             'COM at t=0 (x;y;z)', c(1), c(2), c(3), 'm';
             'Pivot (x;y;z)', pv(1), pv(2), pv(3), 'm';
             'Joint axis (x;y;z)', ax(1), ax(2), ax(3), '-';
             'Jp row 1 (about COM, body frame)', pend.Jp(1,1), pend.Jp(1,2), pend.Jp(1,3), 'kg m^2';
             'Jp row 2 (about COM, body frame)', pend.Jp(2,1), pend.Jp(2,2), pend.Jp(2,3), 'kg m^2';
             'Jp row 3 (about COM, body frame)', pend.Jp(3,1), pend.Jp(3,2), pend.Jp(3,3), 'kg m^2';
             'Gravity vector (x;y;z)', gr(1), gr(2), gr(3), 'm/s^2';
             'Release angle (from vertical)', pend.theta0_deg, [],[], 'deg';
             'External force', pend.forces_desc, [],[], '';
             'End time', T(end), [],[], 's';
             'Reporting time step', T(min(2,nt)) - T(1), [],[], 's';
             'Period (from results)', dap_period, [],[], 's'};
    if exist(xlsFile, 'file'), delete(xlsFile); end
    writecell(props, xlsFile, 'Sheet', 'Properties');
    writecell([hdr; num2cell(dap_results)], xlsFile, 'Sheet', 'Results');
    fprintf('Saved %s (open this one in Excel)\n', xlsFile);
catch err
    warning(['Could not write %s (%s); writecell needs MATLAB R2019a or newer. ' ...
             'Saving a CSV instead.'], xlsFile, err.message);
    % ---- Fallback: CSV (same layout and columns as FreeCAD's old export) ----
    outFile = '__MODEL___DAP3D_results.csv';
    fid = fopen(outFile, 'w');
    fprintf(fid, 'PENDULUM PROPERTIES\nParameter,Value,Unit\n');
    fprintf(fid, 'Solver,DAP3D (MATLAB ode45 standard method),\n');
    fprintf(fid, 'Body,%s,\n', pend.body);
    fprintf(fid, 'Density,%.6g,kg/m^3\n', pend.density);
    fprintf(fid, 'Mass,%.6e,kg\n', m);
    fprintf(fid, 'COM at t=0 (x;y;z),[%.10g; %.10g; %.10g],m\n', pend.com_cad);
    fprintf(fid, 'Pivot (x;y;z),[%.10g; %.10g; %.10g],m\n', pend.pivot);
    fprintf(fid, 'Joint axis (x;y;z),[%.10g; %.10g; %.10g],-\n', pend.axis);
    for k = 1:3
        fprintf(fid, '"Jp row %d (about COM, body frame)",%.6e %.6e %.6e,kg m^2\n', k, pend.Jp(k,:));
    end
    fprintf(fid, 'Gravity vector (x;y;z),[%.10g; %.10g; %.10g],m/s^2\n', pend.gravity);
    fprintf(fid, 'Release angle (from vertical),%.6g,deg\n', pend.theta0_deg);
    fprintf(fid, 'External force,"%s",\n', pend.forces_desc);
    fprintf(fid, 'End time,%.6g,s\nReporting time step,%.6g,s\n', T(end), T(min(2,nt)) - T(1));
    fprintf(fid, 'Period (from results),%.6g,s\n\n', dap_period);
    fprintf(fid, ['SIMULATION RESULTS,theta is measured from the vertical (hanging position) about the joint axis; ' ...
                  'R is the force the pivot applies to the pendulum\n']);
    fprintf(fid, ['t [s],theta [deg],omega [rad/s],alpha [rad/s^2],COM x [m],COM y [m],COM z [m],' ...
                  'COM vx [m/s],COM vy [m/s],COM vz [m/s],COM ax [m/s^2],COM ay [m/s^2],COM az [m/s^2],' ...
                  'Rx [N],Ry [N],Rz [N],|R| [N],KE [J],PE [J],E total [J]']);
    fprintf(fid, '\n');
    ncol = size(dap_results, 2);
    fprintf(fid, [repmat('%.8g,', 1, ncol - 1) '%.8g\n'], dap_results');
    fclose(fid);
    fprintf('Saved %s in %s\n', outFile, pwd);

end
"""


def _xlsx_col(n):
    """0-based column index -> Excel letters (0 -> A, 26 -> AA)."""
    s, n = "", n + 1
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def _write_xlsx(path, sheets):
    """Write a basic .xlsx workbook with the standard library only (no openpyxl).

    sheets: list of dicts with
        name        sheet name
        rows        list of rows; each cell is a str, int, float or None
        bold_rows   set of 0-based row indices drawn in bold
        freeze_rows number of top rows kept visible while scrolling
        widths      list of column widths (characters)
    Numbers are stored as real numbers, so Excel never mistakes them for text,
    whatever the computer's decimal or list separator is."""
    import zipfile
    from xml.sax.saxutils import escape

    ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    rel_ns = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

    def cell(ref, value, style):
        st = ' s="1"' if style else ""
        if value is None or value == "":
            return ""
        if isinstance(value, bool):
            value = str(value)
        if isinstance(value, (int, float)) and math.isfinite(value):
            return f'<c r="{ref}"{st}><v>{repr(float(value)) if isinstance(value, float) else value}</v></c>'
        text = escape(str(value))
        return f'<c r="{ref}" t="inlineStr"{st}><is><t xml:space="preserve">{text}</t></is></c>'

    def sheet_xml(sh):
        parts = [f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="{ns}">']
        fr = sh.get("freeze_rows", 0)
        if fr:
            parts.append(f'<sheetViews><sheetView workbookViewId="0"><pane ySplit="{fr}" '
                         f'topLeftCell="A{fr + 1}" activePane="bottomLeft" state="frozen"/>'
                         f'</sheetView></sheetViews>')
        widths = sh.get("widths")
        if widths:
            parts.append("<cols>" + "".join(
                f'<col min="{i + 1}" max="{i + 1}" width="{w}" customWidth="1"/>'
                for i, w in enumerate(widths)) + "</cols>")
        parts.append("<sheetData>")
        bold = sh.get("bold_rows", set())
        for r, row in enumerate(sh["rows"]):
            cells = "".join(cell(f"{_xlsx_col(c)}{r + 1}", v, r in bold) for c, v in enumerate(row))
            parts.append(f'<row r="{r + 1}">{cells}</row>')
        parts.append("</sheetData></worksheet>")
        return "".join(parts)

    n = len(sheets)
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        + "".join(f'<Override PartName="/xl/worksheets/sheet{i + 1}.xml" '
                  'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                  for i in range(n))
        + '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
        '</Types>')
    root_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        f'<Relationship Id="rId1" Type="{rel_ns}/officeDocument" Target="xl/workbook.xml"/>'
        '</Relationships>')
    workbook = (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="{ns}" xmlns:r="{rel_ns}"><sheets>'
        + "".join(f'<sheet name="{escape(sh["name"][:31])}" sheetId="{i + 1}" r:id="rId{i + 1}"/>'
                  for i, sh in enumerate(sheets))
        + "</sheets></workbook>")
    wb_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        + "".join(f'<Relationship Id="rId{i + 1}" Type="{rel_ns}/worksheet" Target="worksheets/sheet{i + 1}.xml"/>'
                  for i in range(n))
        + f'<Relationship Id="rId{n + 1}" Type="{rel_ns}/styles" Target="styles.xml"/>'
        '</Relationships>')
    styles = (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><styleSheet xmlns="{ns}">'
        '<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font>'
        '<font><b/><sz val="11"/><name val="Calibri"/></font></fonts>'
        '<fills count="2"><fill><patternFill patternType="none"/></fill>'
        '<fill><patternFill patternType="gray125"/></fill></fills>'
        '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
        '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
        '<cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
        '<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/></cellXfs>'
        '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
        '</styleSheet>')

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types)
        z.writestr("_rels/.rels", root_rels)
        z.writestr("xl/workbook.xml", workbook)
        z.writestr("xl/_rels/workbook.xml.rels", wb_rels)
        z.writestr("xl/styles.xml", styles)
        for i, sh in enumerate(sheets):
            z.writestr(f"xl/worksheets/sheet{i + 1}.xml", sheet_xml(sh))


def _material_name_of(obj):
    """Name of the material assigned to a part, wherever it was assigned:
    - the 'Material' property (written by Step 3's material selector), or
    - FreeCAD's own 'ShapeMaterial' (Set Material / Body properties),
    on the part itself, the object it links to, or its child bodies.
    Returns None if no material is assigned."""
    candidates = [obj]
    linked = getattr(obj, "LinkedObject", None)
    if linked is not None and linked is not obj:
        candidates.append(linked)
    candidates += list(getattr(obj, "Group", []) or [])

    def name_from(mat):
        if not mat:
            return None
        if isinstance(mat, str):
            return mat.strip() or None
        if isinstance(mat, dict):
            return mat.get("CardName") or mat.get("Name") or None
        for attr in ("Name", "CardName", "Label"):
            try:
                val = getattr(mat, attr, None)
            except Exception:
                val = None
            if isinstance(val, str) and val.strip():
                return val.strip()
        return None

    # The Step 3 choice wins, then FreeCAD's ShapeMaterial
    for prop in ("Material", "ShapeMaterial"):
        for o in candidates:
            try:
                name = name_from(getattr(o, prop, None))
            except Exception:
                name = None
            if name:
                return name

    # A material exists but has no readable name: describe it by its density
    d = _density_of(obj)
    if d:
        return f"Unnamed material ({d:.0f} kg/m³)"
    return None


def _density_of(obj):
    """Density (kg/m^3) assigned to a part, or None.
    Checks the 'Material' dict written by the material selector first,
    then FreeCAD 1.0 ShapeMaterial, on the object, its linked object and its children."""
    candidates = [obj]
    linked = getattr(obj, "LinkedObject", None)
    if linked is not None and linked is not obj:
        candidates.append(linked)
    candidates += list(getattr(obj, "Group", []) or [])

    for o in candidates:
        mat = getattr(o, "Material", None)
        if isinstance(mat, dict):
            d = _to_kg_m3(mat.get("Density"))
            if d:
                return d
        mat = getattr(o, "ShapeMaterial", None)
        if mat is not None:
            for getter in (
                lambda m: m.getPhysicalValue("Density"),
                lambda m: m.PhysicalProperties.get("Density"),
                lambda m: m.Properties.get("Density"),
            ):
                try:
                    d = _to_kg_m3(getter(mat))
                    if d:
                        return d
                except Exception:
                    pass
    return None


def _global_solids(obj):
    try:
        import Part

        shape = Part.getShape(obj)  # works for Body, App::Part and App::Link
    except Exception:
        shape = obj.Shape
    return shape.Solids


def _mass_properties(obj, density):
    """Return mass [kg], centre of mass [App.Vector, mm, global],
    inertia tensor about the COM [3x3 list, kg m^2, global axes].

    OCC's MatrixOfInertia is for unit density, about each solid's own COM,
    in mm^5.  Multiple solids are combined with the parallel-axis theorem."""
    solids = _global_solids(obj)
    if not solids:
        raise ValueError(f"{obj.Label} has no solids")

    vol = sum(s.Volume for s in solids)
    com = App.Vector(0, 0, 0)
    for s in solids:
        com += s.CenterOfMass * s.Volume
    com = com * (1.0 / vol)

    J = [[0.0] * 3 for _ in range(3)]
    for s in solids:
        M = s.MatrixOfInertia
        d = s.CenterOfMass - com
        dv = [d.x, d.y, d.z]
        dd = _dot(dv, dv)
        for i in range(3):
            for k in range(3):
                J[i][k] += getattr(M, f"A{i + 1}{k + 1}") + s.Volume * (
                    (dd if i == k else 0.0) - dv[i] * dv[k]
                )

    # mm^5 * kg/m^3 -> kg m^2 : (1e-9 m^3/mm^3) * (1e-6 m^2/mm^2) = 1e-15
    J = [[J[i][k] * density * 1e-15 for k in range(3)] for i in range(3)]
    mass = vol * density * 1e-9  # mm^3 -> m^3
    return mass, com, J


def _joint_global_frame(joint):
    """(axis unit vector, origin in mm) of the joint coordinate system, global.
    For a FreeCAD Revolute joint the JCS Z-axis is the rotation axis."""
    for idx in (1, 2):
        plc = getattr(joint, f"Placement{idx}", None)
        ref = getattr(joint, f"Reference{idx}", None)
        if plc is None or not ref:
            continue
        try:
            glob = UtilsAssembly.getJcsGlobalPlc(plc, ref)
        except Exception as e:
            App.Console.PrintWarning(f"getJcsGlobalPlc failed for {joint.Label}: {e}\n")
            continue
        return glob.Rotation.multVec(App.Vector(0, 0, 1)), glob.Base
    return None, None


# ============================================================
# FORCE DRIVERS  (DAP3D force elements 'n' and 'f')
#
# loads (prepared for the solver by _prepare_loads), SI units, global axes:
#   torque  T                        constant moment T about the joint axis   ('n')
#   force   F                        constant force at the COM, fixed in space ('f')
#   th_ref    hanging angle (rad, from the CAD pose): potentials are zero there
# ============================================================

def _prepare_loads(loads, pivot, th_start, th_ref):
    """Force-driver settings -> solver form (adds the reference angles)."""
    if not loads:
        return None
    out = {"th_start": th_start, "th_ref": th_ref}
    if loads.get("torque") is not None:
        out["torque"] = loads["torque"]
    if loads.get("force") is not None:
        out["force"] = dict(loads["force"])
    return out


def _applied_loads(loads, axis, d0, th, om):
    """Force drivers on the pendulum at rotation th (rad, from the CAD pose) and
    angular velocity om. Returns (tau, F, V):
      tau  torque about the joint axis (N m)
      F    sum of the applied forces (N, global), needed for the pivot reaction
      V    potential energy of the driver (J), zero at the hanging position"""
    if not loads:
        return 0.0, [0.0, 0.0, 0.0], 0.0
    u = axis
    tau, F, V = 0.0, [0.0, 0.0, 0.0], 0.0
    th_vert = th - loads["th_ref"]                 # angle from the vertical

    T = loads.get("torque")
    if T is not None:                              # DAP3D 'n': moment T*axis
        tau += T
        V -= T * th_vert

    f = loads.get("force")
    if f is not None:                              # DAP3D 'f', at the COM
        d = _rodrigues(d0, u, th)
        Fg = list(f["F"])
        tau += _dot(u, _cross(d, Fg))
        F = [F[i] + Fg[i] for i in range(3)]
        V += -_dot(Fg, d)                          # like gravity

    return tau, F, V


def _loads_description(loads):
    """Short text describing the force driver (status line, exports)."""
    if not loads:
        return "None"
    parts = []
    if loads.get("torque") is not None:
        parts.append(f"constant torque {loads['torque']:g} N m")
    f = loads.get("force")
    if f is not None:
        F = f["F"]
        parts.append(f"constant force [{F[0]:g}, {F[1]:g}, {F[2]:g}] N at the COM")
    return "; ".join(parts) if parts else "None"


def _integrate_pendulum(mass, J_com, axis, d0, gravity, damping, theta0, omega0, t_end, dt_out,
                        loads=None):
    """Forward dynamics of ONE rigid body on a revolute joint to ground (1 DOF).

        J_O * theta_dd = axis . ( d(theta) x m*g )  +  tau_loads  -  c * theta_d

      d0     : pivot -> COM vector at theta = 0 (m, global)
      J_O    : axis^T J_com axis + m * |d0 perpendicular to axis|^2  (parallel axis)
      loads  : force drivers (see _prepare_loads), or None
    Fixed-step RK4 (<= 1 ms sub-steps), sampled every dt_out.
    Returns (times, thetas, omegas, J_O)."""
    u = axis
    J_O = _dot(u, [_dot(J_com[i], u) for i in range(3)]) + mass * (_dot(d0, d0) - _dot(u, d0) ** 2)
    if J_O <= 0.0:
        raise ValueError("Moment of inertia about the joint axis is zero - check density/geometry")
    F = [mass * g for g in gravity]

    def acc(th, om):
        d = _rodrigues(d0, u, th)
        tau_l = _applied_loads(loads, u, d0, th, om)[0]
        return (_dot(u, _cross(d, F)) + tau_l - damping * om) / J_O

    n_out = int(round(t_end / dt_out))
    sub = max(1, int(math.ceil(dt_out / 1e-3)))
    h = dt_out / sub
    th, om = theta0, omega0
    times, thetas, omegas = [0.0], [th], [om]
    for k in range(n_out):
        for _ in range(sub):
            k1t = om
            k1w = acc(th, om)
            k2t = om + 0.5 * h * k1w
            k2w = acc(th + 0.5 * h * k1t, om + 0.5 * h * k1w)
            k3t = om + 0.5 * h * k2w
            k3w = acc(th + 0.5 * h * k2t, om + 0.5 * h * k2w)
            k4t = om + h * k3w
            k4w = acc(th + h * k3t, om + h * k3w)
            th += h / 6.0 * (k1t + 2 * k2t + 2 * k3t + k4t)
            om += h / 6.0 * (k1w + 2 * k2w + 2 * k3w + k4w)
        times.append((k + 1) * dt_out)
        thetas.append(th)
        omegas.append(om)
    return times, thetas, omegas, J_O


def _pendulum_state(mass, J_O, axis, d0, gravity, damping, th, om, loads=None):
    """Everything else about the pendulum at one instant, from (theta, omega).

    loads: force drivers (see _prepare_loads), or None.

    Returns a dict (SI units, global axes):
      d      pivot -> COM vector          a      COM acceleration
      v      COM velocity                 alpha  angular acceleration
      R      force the pivot applies to the pendulum:  m*a = R + m*g + F_loads
      KE, PE kinetic / potential energy (PE = 0 at pivot height; includes the
             potential of the force drivers, zero at the hanging position)
    """
    u = axis
    d = _rodrigues(d0, u, th)
    F = [mass * g for g in gravity]
    tau_g = _dot(u, _cross(d, F))
    tau_l, F_l, V_l = _applied_loads(loads, u, d0, th, om)
    alpha = (tau_g + tau_l - damping * om) / J_O
    ud = _cross(u, d)                      # direction of COM velocity
    uud = _cross(u, ud)                    # points from COM back to the axis
    v = [om * x for x in ud]               # v = omega (u x d)
    a = [alpha * ud[i] + om * om * uud[i] for i in range(3)]  # tangential + centripetal
    R = [mass * a[i] - F[i] - F_l[i] for i in range(3)]
    return {
        "d": d, "v": v, "a": a, "alpha": alpha, "R": R,
        "KE": 0.5 * J_O * om * om,
        "PE": -_dot(F, d) + V_l,
    }


# ============================================================
# DRIVERS shown in the Simulation Settings list (force drivers only)
# ============================================================

DRIVER_TYPES = [
    ("None (free swing)", None),
    ("Constant torque", "torque"),                # DAP3D n
    ("Constant force (Acting at the COM)", "force"),                  # DAP3D f
]

__title__ = "Assembly Command Create Simulation"
__author__ = "Ondsel"
__url__ = "https://www.freecad.org"


class CommandCreateSimulation:
    def __init__(self):
        pass

    def GetResources(self):
        return {
            "Pixmap": "Assembly_CreateSimulation",
            "MenuText": QT_TRANSLATE_NOOP("Assembly_CreateSimulation", "Simulation"),
            "Accel": "V",
            "ToolTip": QT_TRANSLATE_NOOP(
                "Assembly_CreateSimulation",
                "Creates a new simulation of the current assembly",
            ),
            "CmdType": "ForEdit",
        }

    def IsActive(self):
        if not UtilsAssembly.isAssemblyCommandActive():
            return False

        assembly = UtilsAssembly.activeAssembly()
        joint_types = ["Revolute", "Slider", "Cylindrical"]
        joints = UtilsAssembly.getJointsOfType(assembly, joint_types)
        return len(joints) > 0

    def Activated(self):

        assembly = UtilsAssembly.activeAssembly()
        if not assembly:
            return

        reply = QtWidgets.QMessageBox.question(
            None,
            "Assembly Assistant",
            "🤖 Assembly Assistant\n\n"
            "I will help you prepare this assembly for simulation.\n\n"
            "The first step is to identify the driving axis.\n\n"
            "Continue?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.Cancel,
            QtWidgets.QMessageBox.Yes,
        )

        if reply != QtWidgets.QMessageBox.Yes:
            return

        self.panel = TaskAssemblyCreateSimulation()

        dialog = Gui.Control.showDialog(self.panel)

        if dialog is not None:
            dialog.setAutoCloseOnDeletedDocument(True)
            dialog.setDocumentName(App.ActiveDocument.Name)


######### Simulation Object ###########
class Simulation:
    def __init__(self, feaPy):
        feaPy.Proxy = self
        feaPy.addExtension("App::GroupExtensionPython")

        if not hasattr(feaPy, "aTimeStart"):
            feaPy.addProperty(
                "App::PropertyTime",
                "aTimeStart",
                "Simulation",
                QT_TRANSLATE_NOOP(
                    "App::Property",
                    "Simulation start time.",
                ),
                locked=True,
            )

        if not hasattr(feaPy, "bTimeEnd"):
            feaPy.addProperty(
                "App::PropertyTime",
                "bTimeEnd",
                "Simulation",
                QT_TRANSLATE_NOOP(
                    "App::Property",
                    "Simulation end time.",
                ),
                locked=True,
            )

        if not hasattr(feaPy, "cTimeStepOutput"):
            feaPy.addProperty(
                "App::PropertyTime",
                "cTimeStepOutput",
                "Simulation",
                QT_TRANSLATE_NOOP(
                    "App::Property",
                    "Simulation time step for output.",
                ),
                locked=True,
            )

        if not hasattr(feaPy, "fGlobalErrorTolerance"):
            feaPy.addProperty(
                "App::PropertyFloat",
                "fGlobalErrorTolerance",
                "Simulation",
                QT_TRANSLATE_NOOP(
                    "App::Property",
                    "Integration global error tolerance.",
                ),
                locked=True,
            )

        if not hasattr(feaPy, "jFramesPerSecond"):
            feaPy.addProperty(
                "App::PropertyInteger",
                "jFramesPerSecond",
                "Simulation",
                QT_TRANSLATE_NOOP(
                    "App::Property",
                    "Frames Per Second.",
                ),
                locked=True,
            )

        feaPy.aTimeStart = 0.0
        feaPy.bTimeEnd = 1.0
        feaPy.cTimeStepOutput = 1.0e-2
        feaPy.fGlobalErrorTolerance = 1.0e-6
        feaPy.jFramesPerSecond = 30

        self.motionsChangedCallback = None

    def dumps(self):
        return None

    def loads(self, state):
        return None

    def onChanged(self, feaPy, prop):
        if prop == "Group" and hasattr(self, "motionsChangedCallback"):
            if self.motionsChangedCallback is not None:
                self.motionsChangedCallback()

    def setMotionsChangedCallback(self, callback):
        self.motionsChangedCallback = callback

    def execute(self, feaPy):
        """Do something when doing a recomputation, this method is mandatory"""
        pass

    def getAssembly(self, feaPy):
        assert feaPy.isDerivedFrom("App::FeaturePython"), "Type error"
        for obj in feaPy.InList:
            if obj.isDerivedFrom("Assembly::AssemblyObject"):
                return obj
        return None


class ViewProviderSimulation:
    def __init__(self, vpDoc):
        vpDoc.Proxy = self
        self.Object = vpDoc.Object
        self.setProperties(vpDoc)

    def setProperties(self, vpDoc):
        if not hasattr(vpDoc, "Decimals"):
            vpDoc.addProperty(
                "App::PropertyInteger",
                "Decimals",
                "Space",
                QT_TRANSLATE_NOOP(
                    "App::Property", "The number of decimals to use for calculated texts"
                ),
                locked=True,
            )
            vpDoc.Decimals = 9

    def attach(self, vpDoc):
        """Setup the scene sub-graph of the view provider, this method is mandatory"""
        self.app_obj = vpDoc.Object

        self.display_mode = coin.SoType.fromName("SoFCSelection").createInstance()

        vpDoc.addDisplayMode(self.display_mode, "Wireframe")

    def updateData(self, feaPy, prop):
        """If a property of the handled feature has changed we have the chance to handle this here"""
        pass

    def getDisplayModes(self, vpDoc):
        """Return a list of display modes."""
        return ["Wireframe"]

    def getDefaultDisplayMode(self):
        """Return the name of the default display mode. It must be defined in getDisplayModes."""
        return "Wireframe"

    def onChanged(self, vpDoc, prop):
        """Here we can do something when a single property got changed"""
        pass

    def getIcon(self):
        return ":/icons/Assembly_CreateSimulation.svg"

    def dumps(self):
        """When saving the document this object gets stored using Python's json module.\
                Since we have some un-serializable parts here -- the Coin stuff -- we must define this method\
                to return a tuple of all serializable objects or None."""
        return None

    def loads(self, state):
        """When restoring the serialized object from document we have the chance to set some internals here.\
                Since no data were serialized nothing needs to be done here."""
        return None

    def claimChildren(self):
        return self.app_obj.Group

    def doubleClicked(self, vpDoc):
        task = Gui.Control.activeTaskDialog()
        if task:
            task.reject()

        assembly = vpDoc.Object.Proxy.getAssembly(vpDoc.Object)

        if assembly is None:
            return False

        if UtilsAssembly.activeAssembly() != assembly:
            Gui.ActiveDocument.setEdit(assembly)

        panel = TaskAssemblyCreateSimulation(vpDoc.Object)
        dialog = Gui.Control.showDialog(panel)
        if dialog is not None:
            dialog.setAutoCloseOnDeletedDocument(True)
            dialog.setDocumentName(App.ActiveDocument.Name)

        return True

    def onDelete(self, vobj, subelements):
        for obj in self.claimChildren():
            obj.Document.removeObject(obj.Name)
        return True


########### Motion Object #############
MotionTypes = [
    "Angular",
    "Linear",
]


class Motion:
    def __init__(self, feaPy, motionType=MotionTypes[0], joint=None, formula=""):
        feaPy.Proxy = self

        self.createProperties(feaPy)

        feaPy.MotionType = MotionTypes  # sets the list
        feaPy.MotionType = motionType  # set the initial value
        feaPy.Joint = joint
        feaPy.Formula = formula

    def onDocumentRestored(self, feaPy):
        self.createProperties(feaPy)

    def createProperties(self, feaPy):
        if not hasattr(feaPy, "Joint"):
            feaPy.addProperty(
                "App::PropertyXLinkSubHidden",
                "Joint",
                "Motion",
                QT_TRANSLATE_NOOP("App::Property", "The joint that is moved by the motion"),
                locked=True,
            )

        if not hasattr(feaPy, "Formula"):
            feaPy.addProperty(
                "App::PropertyString",
                "Formula",
                "Motion",
                QT_TRANSLATE_NOOP(
                    "App::Property",
                    "This is the formula of the motion. For example '1.0*time'.",
                ),
                locked=True,
            )

        if not hasattr(feaPy, "MotionType"):
            feaPy.addProperty(
                "App::PropertyEnumeration",
                "MotionType",
                "Motion",
                QT_TRANSLATE_NOOP("App::Property", "The type of the motion"),
                locked=True,
            )

    def dumps(self):
        return None

    def loads(self, state):
        return None

    def onChanged(self, feaPy, prop):
        pass

    def execute(self, feaPy):
        """Do something when doing a recomputation, this method is mandatory"""
        pass

    def getSimulation(self, feaPy):
        for obj in feaPy.InList:
            if hasattr(obj, "Proxy"):
                if hasattr(obj.Proxy, "setMotionsChangedCallback"):
                    return obj
        return None

    def getAssembly(self, feaPy):
        simulation = self.getSimulation(feaPy)
        if simulation is not None:
            return simulation.Proxy.getAssembly(simulation)
        return None


class ViewProviderMotion:
    def __init__(self, vp):
        vp.Proxy = self
        self.updateLabel()

    def attach(self, vpDoc):
        """Setup the scene sub-graph of the view provider, this method is mandatory"""
        self.app_obj = vpDoc.Object

        self.display_mode = coin.SoType.fromName("SoFCSelection").createInstance()

        vpDoc.addDisplayMode(self.display_mode, "Wireframe")

    def updateData(self, feaPy, prop):
        """If a property of the handled feature has changed we have the chance to handle this here"""
        pass

    def getDisplayModes(self, vpDoc):
        """Return a list of display modes."""
        return ["Wireframe"]

    def getDefaultDisplayMode(self):
        """Return the name of the default display mode. It must be defined in getDisplayModes."""
        return "Wireframe"

    def onChanged(self, vpDoc, prop):
        """Here we can do something when a single property got changed"""
        # App.Console.PrintMessage("Change property: " + str(prop) + "\n")
        pass

    def getIcon(self):
        if self.app_obj.MotionType == "Angular":
            return ":/icons/button_rotate.svg"

        return ":/icons/button_right.svg"

    def dumps(self):
        """When saving the document this object gets stored using Python's json module.\
                Since we have some un-serializable parts here -- the Coin stuff -- we must define this method\
                to return a tuple of all serializable objects or None."""
        return None

    def loads(self, state):
        """When restoring the serialized object from document we have the chance to set some internals here.\
                Since no data were serialized nothing needs to be done here."""
        return None

    def doubleClicked(self, vpDoc):
        self.openEditDialog()

    def openEditDialog(self):
        assembly = self.getAssembly()

        if assembly is None:
            return False

        joint = None
        if self.app_obj.Joint is not None:
            joint = self.app_obj.Joint[0]

        dialog = MotionEditDialog(assembly, self.app_obj.MotionType, joint, self.app_obj.Formula)
        if dialog.exec_():
            self.app_obj.MotionType = dialog.motionType
            self.app_obj.Joint = dialog.joint
            self.app_obj.Formula = dialog.formula

            self.updateLabel()

    def updateLabel(self):
        if self.app_obj.Joint is None:
            return

        typeStr = "Linear" if self.app_obj.MotionType == "Linear" else "Angular"

        self.app_obj.Label = "{label} ({type_})".format(
            label=self.app_obj.Joint[0].Label, type_=translate("Assembly", typeStr)
        )

    def getAssembly(self):
        assembly = self.app_obj.Proxy.getAssembly(self.app_obj)

        if assembly is None:
            return None

        if UtilsAssembly.activeAssembly() != assembly:
            Gui.ActiveDocument.setEdit(assembly)

        return assembly


class MotionEditDialog:
    def __init__(self, assembly, motionType=MotionTypes[0], joint=None, formula="5*time"):
        self.assembly = assembly
        self.motionType = motionType
        self.joint = joint
        self.formula = formula

        # Create a non-modal, frameless dialog
        self.dialog = QDialog()
        self.dialog.setWindowFlags(Qt.Popup)
        self.initialPos = QCursor.pos()
        self.dialog.setMinimumSize(500, 200)  # Set a reasonable minimum size

        # Create the joints combobox
        self.joint_combo = QComboBox(self.dialog)
        self.setup_joint_combo()

        # Create the motion type combobox
        self.motion_type_combo = QComboBox(self.dialog)
        self.setup_motiontype_combo()

        def on_motion_type_changed(text):
            self.motionType = text

        self.motion_type_combo.currentTextChanged.connect(on_motion_type_changed)

        def on_joint_changed(index):
            self.joint = self.joint_combo.itemData(index)
            self.setup_motiontype_combo()  # Refresh the motion combo box based on the new joint type

        self.joint_combo.currentIndexChanged.connect(on_joint_changed)

        # Create the line edit for the formula
        formula_edit = QLineEdit(self.dialog)
        formula_edit.setText(self.formula)
        formula_edit.setPlaceholderText(translate("Assembly", "Enter your formula..."))

        # Connect the line edit to update the Formula property
        def on_formula_changed(text):
            self.formula = text

        formula_edit.textChanged.connect(on_formula_changed)

        self.setupHelpSection()

        # Create Ok and Cancel buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel, Qt.Horizontal, self.dialog
        )
        button_box.accepted.connect(self.dialog.accept)
        button_box.rejected.connect(self.dialog.reject)

        # Set up the layout of the dialog
        layout = QGridLayout(self.dialog)

        # Add labels and widgets to the layout
        layout.addWidget(QLabel("Joint"), 0, 0)
        layout.addWidget(self.joint_combo, 0, 1)

        layout.addWidget(QLabel("Motion Type"), 1, 0)
        layout.addWidget(self.motion_type_combo, 1, 1)

        layout.addWidget(QLabel("Formula"), 2, 0)
        layout.addWidget(formula_edit, 2, 1)

        # Add the help label above the buttons
        layout.addWidget(self.help_label0, 3, 0, 1, 2)
        layout.addWidget(self.help_label1, 4, 0, 1, 2)
        layout.addWidget(self.help_label2, 5, 0, 1, 2)
        layout.addWidget(self.help_label3, 6, 0, 1, 2)
        layout.addWidget(self.help_label4, 7, 0, 1, 2)
        layout.addWidget(self.help_label5, 8, 0, 1, 2)
        layout.addWidget(self.help_label6, 9, 0, 1, 2)
        layout.addWidget(self.help_label7, 10, 0, 1, 2)
        # Add the help button and button box in the next row
        layout.addWidget(self.help_button, 11, 0)

        layout.addWidget(button_box, 11, 1)

        self.positionDialog()

    def setupHelpSection(self):

        # Create the help QLabels and set them to be initially hidden
        self.help_label0 = QLabel(
            translate(
                "Assembly",
                "In capital are variables that you need to replace with actual values. More details about each example in its tooltip.",
            ),
            self.dialog,
        )
        self.help_label1 = QLabel(translate("Assembly", " - Linear: C + VEL*time"), self.dialog)
        self.help_label2 = QLabel(
            translate("Assembly", " - Quadratic: C + VEL*time + ACC*time^2"), self.dialog
        )
        self.help_label3 = QLabel(
            translate("Assembly", " - Harmonic: C + AMP*sin(VEL*time - PHASE)"), self.dialog
        )
        self.help_label4 = QLabel(
            translate("Assembly", " - Exponential: C*exp(time/TIMEC)"), self.dialog
        )
        self.help_label5 = QLabel(
            translate(
                "Assembly",
                " - Smooth Step: L1 + (L2 - L1)*((1/2) + (1/pi)*arctan(SLOPE*(time - T0)))",
            ),
            self.dialog,
        )
        self.help_label6 = QLabel(
            translate(
                "Assembly",
                " - Smooth Square Impulse: (H/pi)*(arctan(SLOPE*(time - T1)) - arctan(SLOPE*(time - T2)))",
            ),
            self.dialog,
        )
        self.help_label7 = QLabel(
            translate(
                "Assembly",
                " - Smooth Ramp Top Impulse: ((1/pi)*(arctan(1000*(time - T1)) - arctan(1000*(time - T2))))*(((H2 - H1)/(T2 - T1))*(time - T1) + H1)",
            ),
            self.dialog,
        )

        self.help_label1.setToolTip(
            translate(
                "Assembly",
                """C is a constant offset.
VEL is a velocity or slope or gradient of the straight line.""",
            )
        )
        self.help_label2.setToolTip(
            translate(
                "Assembly",
                """C is a constant offset.
VEL is the velocity or slope or gradient of the straight line.
ACC is the acceleration or coefficient of the second order. The function is a parabola.""",
            )
        )
        self.help_label3.setToolTip(
            translate(
                "Assembly",
                """C is a constant offset.
AMP is the amplitude of the sine wave.
VEL is the angular velocity in radians per second.
PHASE is the phase of the sine wave.""",
            )
        )
        self.help_label4.setToolTip(
            translate(
                "Assembly",
                """C is a constant.
TIMEC is the time constant of the exponential function.""",
            )
        )
        self.help_label5.setToolTip(
            translate(
                "Assembly",
                """L1 is step level before time = T0.
L2 is step level after time = T0.
SLOPE defines the steepness of the transition between L1 and L2 about time = T0. Higher values gives sharper cornered steps. SLOPE = 1000 or greater are suitable.""",
            )
        )
        self.help_label6.setToolTip(
            translate(
                "Assembly",
                """H is the height of the impulse.
T1 is the start of the impulse.
T2 is the end of the impulse.
SLOPE defines the steepness of the transition between 0 and H about time = T1 and T2. Higher values gives sharper cornered impulses. SLOPE = 1000 or greater are suitable.""",
            )
        )
        self.help_label7.setToolTip(
            translate(
                "Assembly",
                """This is similar to the square impulse but the top has a sloping ramp. It is good for building a smooth piecewise linear function by adding a series of these.
T1 is the start of the impulse.
T2 is the end of the impulse.
H1 is the height at T1 at the beginning of the ramp.
H2 is the height at T2 at the end of the ramp.
SLOPE defines the steepness of the transition between 0 and H1 and H2 to 0 about time = T1 and T2 respectively. Higher values gives sharper cornered impulses. SLOPE = 1000 or greater are suitable.""",
            )
        )

        self.help_label0.setWordWrap(True)
        self.help_label1.setWordWrap(True)
        self.help_label2.setWordWrap(True)
        self.help_label3.setWordWrap(True)
        self.help_label4.setWordWrap(True)
        self.help_label5.setWordWrap(True)
        self.help_label6.setWordWrap(True)
        self.help_label7.setWordWrap(True)

        width = 1000
        self.help_label0.setFixedWidth(width)
        self.help_label1.setFixedWidth(width)
        self.help_label2.setFixedWidth(width)
        self.help_label3.setFixedWidth(width)
        self.help_label4.setFixedWidth(width)
        self.help_label5.setFixedWidth(width)
        self.help_label6.setFixedWidth(width)
        self.help_label7.setFixedWidth(width)

        self.help_label0.setVisible(False)
        self.help_label1.setVisible(False)
        self.help_label2.setVisible(False)
        self.help_label3.setVisible(False)
        self.help_label4.setVisible(False)
        self.help_label5.setVisible(False)
        self.help_label6.setVisible(False)
        self.help_label7.setVisible(False)

        self.help_label1.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.help_label2.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.help_label3.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.help_label4.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.help_label5.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.help_label6.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.help_label7.setTextInteractionFlags(Qt.TextSelectableByMouse)
        # Create the Help button
        self.help_button = QPushButton(translate("Assembly", "Help"), self.dialog)

        # Slot to toggle help visibility and button text
        def toggle_help():
            show = not self.help_label1.isVisible()
            self.help_label0.setVisible(show)
            self.help_label1.setVisible(show)
            self.help_label2.setVisible(show)
            self.help_label3.setVisible(show)
            self.help_label4.setVisible(show)
            self.help_label5.setVisible(show)
            self.help_label6.setVisible(show)
            self.help_label7.setVisible(show)

            if show:
                self.help_button.setText(translate("Assembly", "Hide help"))
            else:
                self.help_button.setText(translate("Assembly", "Help"))

            self.positionDialog()

        self.help_button.clicked.connect(toggle_help)

    def positionDialog(self):
        self.dialog.adjustSize()

        # Get the screen where the mouse is located
        screen = QGuiApplication.screenAt(self.initialPos)
        screen_geometry = (
            screen.availableGeometry()
            if screen
            else QApplication.primaryScreen().availableGeometry()
        )

        # Calculate the position of the dialog to ensure it stays within the screen
        dialog_position = self.initialPos

        # Adjust position to keep the dialog within the screen bounds
        if dialog_position.x() + self.dialog.width() > screen_geometry.right():
            dialog_position.setX(screen_geometry.right() - self.dialog.width())
        if dialog_position.y() + self.dialog.height() > screen_geometry.bottom():
            dialog_position.setY(screen_geometry.bottom() - self.dialog.height())

        # Ensure the dialog does not go above or to the left of the screen
        if dialog_position.x() < screen_geometry.left():
            dialog_position.setX(screen_geometry.left())
        if dialog_position.y() < screen_geometry.top():
            dialog_position.setY(screen_geometry.top())

        # Move the dialog to the final position
        self.dialog.move(dialog_position)

    def setup_joint_combo(self):
        # Function to set up the joint combo box based on the selected motion type

        self.joint_combo.clear()  # Clear existing items

        jointTypes = ["Revolute", "Slider", "Cylindrical"]

        joints = UtilsAssembly.getJointsOfType(self.assembly, jointTypes)

        # Add joints to the combo box with labels and icons
        for joint in joints:
            joint_label = joint.Label
            joint_icon = QIcon(joint.ViewObject.Icon)
            self.joint_combo.addItem(joint_icon, joint_label, userData=joint)

        # Set the current value based on the object's Joint property
        if self.joint in joints:
            self.joint_combo.setCurrentText(self.joint.Label)
        elif len(joints) > 0:
            self.joint = joints[0]

    def setup_motiontype_combo(self):
        self.motion_type_combo.clear()  # Clear existing items

        if self.joint is None:
            return

        if self.joint.JointType == "Revolute":
            types = ["Angular"]
        elif self.joint.JointType == "Slider":
            types = ["Linear"]
        else:
            types = ["Angular", "Linear"]

        self.motion_type_combo.addItems(types)

        # Set current value based on the object's MotionType
        if self.motionType in types:
            self.motion_type_combo.setCurrentText(self.motionType)
        else:
            # self.motionType is no longer available, so we reset it to first entry
            self.motionType = types[0]

    def exec_(self):
        return self.dialog.exec()


######### Create Simulation Task ###########
class TaskAssemblyCreateSimulation(QtCore.QObject):
    def __init__(self, simFeaturePy=None):
        self.currentStep = 0
        super().__init__()
        self.assembly = UtilsAssembly.activeAssembly()

        self.initialPlcs = UtilsAssembly.saveAssemblyPartsPlacements(self.assembly)

        self.doc = self.assembly.Document
        self.gui_doc = Gui.getDocument(self.doc)

        self.view = self.gui_doc.activeView()

        if not self.assembly or not self.view or not self.doc:
            return

        self.runKinematicsTimer = QtCore.QTimer()
        self.runKinematicsTimer.setSingleShot(True)
        self.runKinematicsTimer.timeout.connect(self.displayLastFrame)

        self.animationTimer = QtCore.QTimer()
        self.animationTimer.setInterval(50)  # ms
        self.animationTimer.timeout.connect(self.playAnimation)

        self.form = Gui.PySideUic.loadUi(":/panels/TaskAssemblyCreateSimulation.ui")

        layout = self.form.verticalLayout_2

        # --------------------------------------------------
        # Simulation Assistant
        # --------------------------------------------------

        assistantGroup = QtWidgets.QGroupBox("🤖 Simulation Assistant")

        self.assistantLayout = QtWidgets.QVBoxLayout()

        self.assistantTitle = QtWidgets.QLabel(
            "<h2>🤖 Simulation Assistant</h2>"
        )

        self.assistantLayout.addWidget(self.assistantTitle)

        self.assistantStatus = QtWidgets.QLabel(
            "<b>Step 1 of 6</b><br><br>"
            "Let's identify the driving axis.<br><br>"
            "Press <b>Highlight Axis</b> to begin."
        )

        self.assistantStatus.setWordWrap(True)

        self.assistantLayout.addWidget(self.assistantStatus)

        self.assistantButtonYes = QtWidgets.QPushButton("✓ Yes")
        self.assistantButtonNo = QtWidgets.QPushButton("↻ Recalculate")

        self.assistantButtonYes.hide()
        self.assistantButtonNo.hide()

        self.assistantLayout.addWidget(self.assistantButtonYes)
        self.assistantLayout.addWidget(self.assistantButtonNo)

        self.highlightAxisButton = QtWidgets.QPushButton("Highlight Axis")
        self.RecheckButton = QtWidgets.QPushButton("Recheck assembly")

        self.infoButton = QtWidgets.QPushButton("ℹ️ Detailed Assembly Info")

        self.axisYesButton = QtWidgets.QPushButton("✓ Yes")

        self.axisChooseButton = QtWidgets.QPushButton("Choose Another")

        self.highlightAxisButton.clicked.connect(
            self.onAssistantButton
        )

        self.RecheckButton.clicked.connect(
            self.RecheckAssembly
        )

        self.infoButton.clicked.connect(
            self.show_assembly_info
        )

        self.backButton = QtWidgets.QPushButton("⬅ Back")
        self.backButton.clicked.connect(self.goBackStep)
        self.backButton.setEnabled(False)  # Disabled at Step 0

        self.assistantLayout.addWidget(self.highlightAxisButton)
        self.assistantLayout.addWidget(self.RecheckButton)
        self.assistantLayout.addWidget(self.backButton)
        self.assistantLayout.addWidget(self.infoButton)

        assistantGroup.setLayout(self.assistantLayout)

        # Put the assistant at the TOP of the panel
        layout.insertWidget(0, assistantGroup)

        self.analyseAssembly()

        self.form.motionList.installEventFilter(self)
        self.setSpinboxPrecision(self.form.TimeStartSpinBox, 9)
        self.setSpinboxPrecision(self.form.TimeEndSpinBox, 9)
        self.setSpinboxPrecision(self.form.TimeStepOutputSpinBox, 9)
        self.setSpinboxPrecision(self.form.GlobalErrorToleranceSpinBox, 9, App.Units.Length)
        self.form.motionList.itemDoubleClicked.connect(self.onItemDoubleClicked)
        self.form.TimeStartSpinBox.valueChanged.connect(self.onTimeStartChanged)
        self.form.TimeEndSpinBox.valueChanged.connect(self.onTimeEndChanged)
        self.form.TimeStepOutputSpinBox.valueChanged.connect(self.onTimeStepOutputChanged)
        self.form.GlobalErrorToleranceSpinBox.valueChanged.connect(
            self.onGlobalErrorToleranceChanged
        )
        self.form.RunKinematicsButton.clicked.connect(self.runKinematics)
        self.form.frameSlider.valueChanged.connect(self.onFrameChanged)
        self.form.FramesPerSecondSpinBox.valueChanged.connect(self.onFramesPerSecondChanged)
        self.form.PlayBackwardButton.clicked.connect(self.animationTimerStartBackward)
        self.form.PlayForwardButton.clicked.connect(self.animationTimerStartForward)
        self.form.StepBackwardButton.clicked.connect(self.stepBackward)
        self.form.StepForwardButton.clicked.connect(self.stepForward)
        self.form.StopButton.clicked.connect(self.stopAnimation)
        self.form.AddButton.clicked.connect(self.addMotionClicked)
        self.form.RemoveButton.clicked.connect(self.deleteSelectedMotions)
        self.form.groupBox_player.hide()

        if simFeaturePy:
            self.simFeaturePy = simFeaturePy
            App.setActiveTransaction("Edit " + simFeaturePy.Label + " Simulation")
            self.onMotionsChanged()
        else:
            App.setActiveTransaction("Create Simulation")
            self.createSimulationObject()

        self.setUiInitialValues()

        self.simFeaturePy.Proxy.setMotionsChangedCallback(self.onMotionsChanged)

        self.currentFrm = 1
        self.startFrm = 1
        self.endFrm = 100
        self.fps = 30
        self.deltaTime = 1.0 / self.fps
        self.startTime = time.time()
        self.index = 0

    def analyseAssembly(self):
        self.currentStep = 0

        bodies = []
        revolute = 0
        fixed = 0
        slider = 0

        # Reset detected bodies
        self.groundedBody = None
        self.movingBody = None

        App.Console.PrintMessage("\n=== Starting Assembly Analysis ===\n")

        # --------------------------------------------------
        # 1. Collect all components in active assembly
        # --------------------------------------------------
        for obj in self.doc.Objects:
            is_component = (
                obj.isDerivedFrom("PartDesign::Body") or 
                obj.isDerivedFrom("App::Part") or 
                obj.isDerivedFrom("App::Link")
            )

            if is_component and (
                (hasattr(obj, "getParentGeoFeatureGroup") and obj.getParentGeoFeatureGroup() == self.assembly) or 
                (hasattr(self.assembly, "Group") and obj in self.assembly.Group)
            ):
                bodies.append(obj)
                App.Console.PrintMessage(f"Found Component: {obj.Label} ({obj.Name})\n")

        # --------------------------------------------------
        # 2. Extract Grounded Objects and count Joints
        # --------------------------------------------------
        # DEBUG: Print all objects and their properties
        App.Console.PrintMessage("\n=== DEBUG: Searching for Joints ===\n")
        for obj in self.doc.Objects:
            # Print basic info
            App.Console.PrintMessage(f"Object: {obj.Name} ({obj.Label})")
            App.Console.PrintMessage(f"  TypeId: {obj.TypeId}")
            
            # Print all properties that might relate to joints
            for prop in dir(obj):
                if "Joint" in prop or "joint" in prop or "Type" in prop:
                    try:
                        val = getattr(obj, prop)
                        App.Console.PrintMessage(f"  {prop}: {val}")
                    except:
                        pass
            App.Console.PrintMessage("---")
        
        grounded_objects = set()

        for obj in self.doc.Objects:
            is_grounded_joint = (
                "Grounded" in obj.Name or 
                "Grounded" in str(getattr(obj, "TypeId", "")) or
                getattr(obj, "JointType", "") in ["Grounded", "Fixed"]
            )

            if is_grounded_joint:
                for prop in ["ObjectToGround", "DataObjectToGround", "Target"]:
                    target = getattr(obj, prop, None)
                    if target:
                        grounded_objects.add(target)

                ref1 = getattr(obj, "Reference1", None)
                if ref1:
                    if isinstance(ref1, (list, tuple)) and len(ref1) > 0:
                        elem = ref1[0]
                        if isinstance(elem, (list, tuple)) and len(elem) > 0:
                            grounded_objects.add(elem[0])
                        else:
                            grounded_objects.add(elem)

            if hasattr(obj, "JointType"):
                if obj.JointType == "Revolute":
                    revolute += 1
                elif obj.JointType == "Fixed":
                    fixed += 1
                elif obj.JointType == "Slider":
                    slider += 1

        # --------------------------------------------------
        # 3. Match Grounded Objects to Assembly Components
        # --------------------------------------------------
        grounded_count = 0

        for body in bodies:
            linked_obj = getattr(body, "LinkedObject", None)
            
            if body in grounded_objects or (linked_obj and linked_obj in grounded_objects):
                grounded_count += 1
                if self.groundedBody is None:
                    self.groundedBody = body

        for body in bodies:
            if body != self.groundedBody:
                self.movingBody = body
                break

        moving_count = max(0, len(bodies) - grounded_count)

        # Kept for the Excel export (Bodies sheet)
        self.assemblyBodies = list(bodies)
        self.groundedBodies = [
            b for b in bodies
            if b in grounded_objects
            or (getattr(b, "LinkedObject", None) is not None and b.LinkedObject in grounded_objects)
        ]

        # Clean Console Summary
        App.Console.PrintMessage(f"Total Bodies: {len(bodies)}\n")
        App.Console.PrintMessage(f"Grounded Body: {self.groundedBody.Label if self.groundedBody else 'None'}\n")
        App.Console.PrintMessage(f"Moving Body: {self.movingBody.Label if self.movingBody else 'None'}\n")
        App.Console.PrintMessage("=== Analysis Complete ===\n\n")

        # --------------------------------------------------
        # 4. Update Assistant UI
        # --------------------------------------------------
        self.assistantStep(
            1,
            6,
            "Assembly Analysis",
            f"""
            I analysed your assembly.<br><br>

            <b>Bodies</b><br>
            • Total Bodies : {len(bodies)}<br>
            • Grounded : {grounded_count}<br>
            • Moving : {moving_count}<br><br>

            <b>Joints</b><br>
            • Revolute : {revolute}<br>
            • Fixed : {fixed}<br>
            • Slider : {slider}<br><br>

            Does this look correct?
            """
        )

        self.highlightAxisButton.setText("Confirm Assembly")
        self.highlightAxisButton.show()

        self.RecheckButton.setText("Recheck assembly")
        self.RecheckButton.show()

        # Step 1 has detailed assembly information
        self.infoButton.show()

        self.updateBackButtonState()

    def RecheckAssembly(self):
        # If the assembly analysis is not correct
        # Re-analyse the assembly and reset the assistant
        
        if self.RecheckButton.text() == "Recheck assembly":
            
            self.analyseAssembly()
            return
        
        # Re-analyse the assembly and rehighlight the driving axis
        
        if self.RecheckButton.text() == "Recheck axis":
                    
            self.highlightDrivingAxis()
            return


    def onAssistantButton(self):

        # ------------------------------------------
        # Step 0: Assembly analysis confirmed
        # ------------------------------------------

        if self.highlightAxisButton.text() == "Confirm Assembly":

            self.highlightDrivingAxis()
            self.infoButton.hide()
            return

        # ------------------------------------------
        # Step 1/2: Driving axis highlighted
        # ------------------------------------------

        if self.highlightAxisButton.text() == "Confirm Axis":

            self.showInitialBodyState()
            return
    
    def hideMaterialSelector(self):
        """Hide the embedded material selector (it belongs to the Initial Body State step only)."""
        if hasattr(self, "mat_container"):
            self.mat_container.hide()

    def hidePendulumControls(self):
        """Hide the Step 6 buttons, stop any animation and put the part back
        where it was, so no Step 6 controls or motion leak into other steps."""
        self.stopPendulum()
        if not getattr(self, "_pendulumControlsShown", False):
            return
        for btn in getattr(self, "pendulumButtons", []):
            btn.hide()
        if hasattr(self, "simSettingsGroup"):
            self.simSettingsGroup.hide()
        self._removeGravityArrow()
        self._removeDriverGlyph()
        self._pendulumControlsShown = False
        if self.movingBody is not None and hasattr(self, "bodyPlacement0"):
            self.movingBody.Placement = self.bodyPlacement0

    def assistantStep(self, step, total, title, text):

        # Every step except 'Initial Body State' is drawn through this method,
        # so hiding here guarantees the selector never leaks into other steps.
        self.hideMaterialSelector()
        self.hidePendulumControls()

        self.assistantTitle.setText(
            f"<h2>🤖 Simulation Assistant</h2>"
            f"<h3>Step {step} of {total}</h3>"
        )

        self.assistantStatus.setText(
            f"<b>{title}</b><br><br>{text}"
        )

        QtWidgets.QApplication.processEvents()

    def highlightDrivingAxis(self):
        self.currentStep = 1
        import pivy.coin as coin
        
        App.Console.PrintMessage("\n=== Highlight Driving Axis ===\n")

        # ------------------------------------------
        # Remove previous highlight
        # ------------------------------------------
        try:
            if hasattr(self, "axisGraphic"):
                self.view.getSceneGraph().removeChild(self.axisGraphic)
        except Exception:
            pass

        root = self.view.getSceneGraph()

        # ------------------------------------------
        # Define joint handlers
        # ------------------------------------------
        
        joint_handlers = {
            "Revolute": self._extract_revolute_axis,
            "Slider": self._extract_slider_axis,
            "Cylindrical": self._extract_cylindrical_axis,
            "Fixed": self._extract_fixed_axis,
        }

        # ------------------------------------------
        # Find the first joint
        # ------------------------------------------
        
        found_joint = None
        found_type = None
        axis = None
        origin = None

        for obj in self.doc.Objects:
            # Try to get joint type - FIXED: handle None
            joint_type = None
            for prop in ["JointType", "Type", "JointTypeId"]:
                if hasattr(obj, prop):
                    val = getattr(obj, prop)
                    if val is not None:
                        joint_type = str(val)
                    break
            
            # If still None, try checking name and references
            if not joint_type:
                if "Joint" in obj.Name or "Joint" in obj.Label:
                    if hasattr(obj, "Reference1") or hasattr(obj, "Reference2"):
                        # Try to determine type from other properties
                        if hasattr(obj, "JointType"):
                            joint_type = str(obj.JointType)
                        else:
                            joint_type = "Unknown"
                else:
                    continue
            
            # Skip if still None
            if joint_type is None:
                continue
            
            # Debug: Print what we found
            App.Console.PrintMessage(f"Checking object: {obj.Name} - Type: {joint_type}\n")
            
            # Find matching handler - FIXED: handle None safely
            handler = None
            matched_type = None
            for known_type in joint_handlers:
                # Safely check if joint_type contains known_type or vice versa
                if joint_type is not None and known_type is not None:
                    if known_type.lower() in joint_type.lower() or joint_type.lower() in known_type.lower():
                        handler = joint_handlers[known_type]
                        matched_type = known_type
                        break
            
            if handler is None:
                App.Console.PrintMessage(f"Skipping unknown joint: {obj.Name} (Type: {joint_type})\n")
                continue
            
            # Extract axis and origin using the handler
            try:
                axis, origin = handler(obj)
                if axis is not None and origin is not None:
                    found_joint = obj
                    found_type = matched_type
                    break
            except Exception as e:
                App.Console.PrintError(f"Error extracting from {obj.Name}: {e}\n")
                continue

        # ------------------------------------------
        # If no joint found, show error
        # ------------------------------------------
        
        if found_joint is None:
            self.assistantStep(
                1,
                6,
                "⚠️ No Driving Joint Found",
                """
                <b>⚠️ No detectable joint found.</b><br><br>
                
                I could not find a revolute, slider, or cylindrical joint.<br><br>
                
                Please ensure:<br>
                • You have created at least one joint<br>
                • The joint type is supported<br><br>
                
                <b>Supported types:</b> Revolute, Slider, Cylindrical<br><br>
                
                Click <b>"Recheck"</b> to scan again.
                """
            )
            self.RecheckButton.setText("Recheck axis")
            self.RecheckButton.clicked.disconnect()
            self.RecheckButton.clicked.connect(self.recheckJoints)
            self.RecheckButton.show()
            return

        # ------------------------------------------
        # Normalize axis
        # ------------------------------------------
        
        if axis.Length > 0:
            axis.normalize()
        else:
            axis = App.Vector(0, 0, 1)

        App.Console.PrintMessage(f"FOUND JOINT: {found_joint.Name}\n")
        App.Console.PrintMessage(f"Type: {found_type}\n")
        App.Console.PrintMessage(f"Origin: {origin}\n")
        App.Console.PrintMessage(f"Axis: {axis}\n")

        # ------------------------------------------
        # Create the axis line in 3D view
        # ------------------------------------------
        
        length = 300
        p1 = origin - axis * (length / 2)
        p2 = origin + axis * (length / 2)

        sep = coin.SoSeparator()

        # Color based on joint type
        colors = {
            "Revolute": (0.0, 0.45, 1.0),    # Blue
            "Slider": (0.0, 1.0, 0.45),      # Green
            "Cylindrical": (1.0, 0.45, 0.0), # Orange
            "Fixed": (1.0, 0.0, 0.0),        # Red
        }
        color = colors.get(found_type, (0.0, 0.45, 1.0))

        material = coin.SoMaterial()
        material.diffuseColor = color
        material.emissiveColor = color

        drawStyle = coin.SoDrawStyle()
        drawStyle.lineWidth = 5

        coords = coin.SoCoordinate3()
        coords.point.setValues(
            0,
            2,
            [
                (p1.x, p1.y, p1.z),
                (p2.x, p2.y, p2.z),
            ],
        )

        line = coin.SoLineSet()
        sep.addChild(material)
        sep.addChild(drawStyle)
        sep.addChild(coords)
        sep.addChild(line)

        root.addChild(sep)
        self.axisGraphic = sep

        # ------------------------------------------
        # Store joint info for later use
        # ------------------------------------------
        
        self.currentJoint = found_joint
        self.currentJointType = found_type
        self.currentAxis = axis
        self.currentOrigin = origin

        # ------------------------------------------
        # Update Assistant
        # ------------------------------------------
        
        joint_type_display = {
            "Revolute": "Revolute Joint (Rotation Axis)",
            "Slider": "Slider Joint (Translation Direction)",
            "Cylindrical": "Cylindrical Joint (Combined Axis)",
            "Fixed": "Fixed Joint (No Motion)",
        }.get(found_type, "Driving Axis")

        self.assistantStep(
            2,
            6,
            f"{joint_type_display} Detected",
            f"""
            I have highlighted the detected axis.<br><br>
            
            <b>Joint Name:</b> {found_joint.Label}<br>
            <b>Joint Type:</b> {found_type}<br><br>
            
            <b>Axis Direction:</b><br>
            [{axis.x:.6f}, {axis.y:.6f}, {axis.z:.6f}]<br><br>
            
            <b>Origin Position:</b><br>
            [{origin.x:.6f}, {origin.y:.6f}, {origin.z:.6f}] mm<br><br>
            
            <b>Connected Bodies:</b><br>
            • {self._get_joint_body(found_joint, 1)}<br>
            • {self._get_joint_body(found_joint, 2)}<br><br>
            
            <b>Is this axis correct?</b>
            """
        )

        self.highlightAxisButton.setText("Confirm Axis")
        self.highlightAxisButton.show()

        self.RecheckButton.setText("Recheck axis")
        self.RecheckButton.show()
        
        self.updateBackButtonState()
    # ============================================================
    # JOINT EXTRACTION HELPERS
    # ============================================================

    def _extract_revolute_axis(self, obj):
        """Extract axis and origin from a Revolute joint"""
        
        # Try to get from Reference2 (common for revolute)
        try:
            if hasattr(obj, "Reference2"):
                ref = obj.Reference2
                if isinstance(ref, (list, tuple)) and len(ref) > 0:
                    body = ref[0]
                    if isinstance(body, (list, tuple)):
                        body = body[0]
                    
                    # Try to get face from reference
                    if len(ref) > 1 and isinstance(ref[1], (list, tuple)):
                        face_name = ref[1][0]
                        if hasattr(body, "Shape"):
                            face = body.Shape.getElement(face_name)
                            origin = face.CenterOfMass
                            # Axis is along the face normal (cylindrical face)
                            # For revolute, we need the axis of the cylindrical face
                            if hasattr(face, "Surface") and hasattr(face.Surface, "Axis"):
                                axis = face.Surface.Axis
                            else:
                                # Fallback: use placement Z-axis
                                if hasattr(obj, "Placement"):
                                    axis = obj.Placement.Rotation.multVec(App.Vector(0, 0, 1))
                                else:
                                    axis = App.Vector(0, 0, 1)
                            return axis, origin
        except Exception as e:
            App.Console.PrintMessage(f"Revolute extraction (Reference2): {e}\n")
        
        # Fallback: use placement
        if hasattr(obj, "Placement"):
            origin = obj.Placement.Base
            axis = obj.Placement.Rotation.multVec(App.Vector(0, 0, 1))
            return axis, origin
        elif hasattr(obj, "Placement2"):
            origin = obj.Placement2.Base
            axis = obj.Placement2.Rotation.multVec(App.Vector(0, 0, 1))
            return axis, origin
        
        return App.Vector(0, 0, 1), App.Vector(0, 0, 0)

    def _extract_slider_axis(self, obj):
        """Extract axis and origin from a Slider joint"""
        
        # Slider joints: axis is the translation direction
        try:
            if hasattr(obj, "Placement"):
                origin = obj.Placement.Base
                axis = obj.Placement.Rotation.multVec(App.Vector(0, 0, 1))
                return axis, origin
            elif hasattr(obj, "Placement1"):
                origin = obj.Placement1.Base
                axis = obj.Placement1.Rotation.multVec(App.Vector(0, 0, 1))
                return axis, origin
        except:
            pass
        
        # Try to get from reference
        try:
            if hasattr(obj, "Reference1"):
                ref = obj.Reference1
                if isinstance(ref, (list, tuple)) and len(ref) > 0:
                    body = ref[0]
                    if isinstance(body, (list, tuple)):
                        body = body[0]
                    if hasattr(body, "Shape"):
                        origin = body.Shape.CenterOfMass
                        # Axis from placement
                        if hasattr(body, "Placement"):
                            axis = body.Placement.Rotation.multVec(App.Vector(0, 0, 1))
                        else:
                            axis = App.Vector(0, 0, 1)
                        return axis, origin
        except:
            pass
        
        return App.Vector(0, 0, 1), App.Vector(0, 0, 0)

    def _extract_cylindrical_axis(self, obj):
        """Extract axis and origin from a Cylindrical joint"""
        
        # Cylindrical joints have both rotation and translation along the same axis
        # Use similar logic to revolute
        try:
            if hasattr(obj, "Placement"):
                origin = obj.Placement.Base
                axis = obj.Placement.Rotation.multVec(App.Vector(0, 0, 1))
                return axis, origin
            elif hasattr(obj, "Placement2"):
                origin = obj.Placement2.Base
                axis = obj.Placement2.Rotation.multVec(App.Vector(0, 0, 1))
                return axis, origin
        except:
            pass
        
        # Try to get from reference
        try:
            if hasattr(obj, "Reference1"):
                ref = obj.Reference1
                if isinstance(ref, (list, tuple)) and len(ref) > 0:
                    body = ref[0]
                    if isinstance(body, (list, tuple)):
                        body = body[0]
                    if hasattr(body, "Shape"):
                        origin = body.Shape.CenterOfMass
                        if hasattr(body, "Placement"):
                            axis = body.Placement.Rotation.multVec(App.Vector(0, 0, 1))
                        else:
                            axis = App.Vector(0, 0, 1)
                        return axis, origin
        except:
            pass
        
        return App.Vector(0, 0, 1), App.Vector(0, 0, 0)

    def show_assembly_info(self=None):
        """Procedural Reality Check dialog with an aligned, compact Close button."""
        doc = App.ActiveDocument
        if not doc:
            return

        def get_target(ref):
            while isinstance(ref, (list, tuple)) and ref:
                ref = ref[0]
            return ref if hasattr(ref, "Label") else None

        # 1. Collect Grounded Parts
        grounded = []
        for obj in doc.Objects:
            if hasattr(obj, "ObjectToGround") or hasattr(obj, "DataObjectToGround"):
                ref = getattr(
                    obj, "ObjectToGround", getattr(obj, "DataObjectToGround", None)
                )
                target = get_target(ref)
                if target and target.Label not in grounded:
                    grounded.append(target.Label)

        # 2. Helper to Calculate Current RHR Angle
        def calc_angle(joint_obj):
            b1 = get_target(
                getattr(
                    joint_obj,
                    "Reference1",
                    getattr(joint_obj, "DataReference1", None),
                )
            )
            b2 = get_target(
                getattr(
                    joint_obj,
                    "Reference2",
                    getattr(joint_obj, "DataReference2", None),
                )
            )
            if not b1 or not b2:
                return None, None, None

            p1 = getattr(
                joint_obj,
                "DataPlacement1",
                getattr(joint_obj, "Placement1", App.Placement()),
            )
            p2 = getattr(
                joint_obj,
                "DataPlacement2",
                getattr(joint_obj, "Placement2", App.Placement()),
            )
            o1 = getattr(
                joint_obj,
                "DataOffset1",
                getattr(joint_obj, "Offset1", App.Placement()),
            )
            o2 = getattr(
                joint_obj,
                "DataOffset2",
                getattr(joint_obj, "Offset2", App.Placement()),
            )

            jcs1 = b1.Placement * p1 * o1
            jcs2 = b2.Placement * p2 * o2

            if b2.Label in grounded:
                base_jcs, moving_jcs = jcs2, jcs1
            else:
                base_jcs, moving_jcs = jcs1, jcs2

            rel_p = base_jcs.inverse() * moving_jcs
            x_moving = rel_p.Rotation.multVec(App.Vector(1, 0, 0))
            angle_deg = math.degrees(math.atan2(x_moving.y, x_moving.x))
            return angle_deg, b1, b2

        # 3. Helper to Adjust Angle and Drive 3D Viewport
        def adjust_angle(joint_obj, label_widget):
            curr_angle, b1, b2 = calc_angle(joint_obj)
            if curr_angle is None:
                return

            target_angle, ok = QtWidgets.QInputDialog.getDouble(
                dialog,
                "Set Joint Angle",
                f"Enter target angle for {joint_obj.Label} (°):",
                value=curr_angle,
                decimals=2,
            )
            if not ok:
                return

            p1 = getattr(
                joint_obj,
                "DataPlacement1",
                getattr(joint_obj, "Placement1", App.Placement()),
            )
            p2 = getattr(
                joint_obj,
                "DataPlacement2",
                getattr(joint_obj, "Placement2", App.Placement()),
            )
            o1 = getattr(
                joint_obj,
                "DataOffset1",
                getattr(joint_obj, "Offset1", App.Placement()),
            )
            o2 = getattr(
                joint_obj,
                "DataOffset2",
                getattr(joint_obj, "Offset2", App.Placement()),
            )

            if b2.Label in grounded:
                base_body, moving_body = b2, b1
                p_base, p_moving = p2, p1
                o_base, o_moving = o2, o1
            else:
                base_body, moving_body = b1, b2
                p_base, p_moving = p1, p2
                o_base, o_moving = o1, o2

            base_jcs = base_body.Placement * p_base * o_base
            moving_jcs = moving_body.Placement * p_moving * o_moving

            rel_p = base_jcs.inverse() * moving_jcs
            new_rel_rotation = App.Rotation(App.Vector(0, 0, 1), target_angle)
            new_rel_placement = App.Placement(rel_p.Base, new_rel_rotation)

            new_moving_jcs = base_jcs * new_rel_placement
            connector_offset = p_moving * o_moving
            moving_body.Placement = new_moving_jcs * connector_offset.inverse()

            doc.recompute()

            new_angle, _, _ = calc_angle(joint_obj)
            label_widget.setText(
                f"• {joint_obj.Label}: {b1.Label} ↔ {b2.Label} | Angle: {new_angle:.2f}°"
            )

        # 4. Dialog Assembly
        dialog = QtWidgets.QDialog()
        dialog.setWindowTitle("Reality Check - Assembly Diagnostics")
        dialog.resize(500, 300)

        layout = QtWidgets.QVBoxLayout(dialog)

        # Grounded Section
        layout.addWidget(QtWidgets.QLabel("<b>=== Grounded Parts ===</b>"))
        layout.addWidget(
            QtWidgets.QLabel(", ".join(grounded) if grounded else "None")
        )
        layout.addSpacing(10)

        # Joint Section
        layout.addWidget(QtWidgets.QLabel("<b>=== Joint Connections ===</b>"))

        has_joints = False
        for obj in doc.Objects:
            if hasattr(obj, "Reference1") or hasattr(obj, "DataReference1"):
                angle, b1, b2 = calc_angle(obj)
                if angle is not None:
                    has_joints = True
                    row = QtWidgets.QHBoxLayout()

                    lbl = QtWidgets.QLabel(
                        f"• {obj.Label}: {b1.Label} ↔ {b2.Label} | Angle: {angle:.2f}°"
                    )
                    btn = QtWidgets.QPushButton("Adjust Angle")

                    btn.clicked.connect(
                        lambda checked=False, j=obj, l=lbl: adjust_angle(j, l)
                    )

                    row.addWidget(lbl)
                    row.addStretch()
                    row.addWidget(btn)
                    layout.addLayout(row)

        if not has_joints:
            layout.addWidget(QtWidgets.QLabel("No joints detected."))

        layout.addStretch()

        # Small Right-Aligned Close Button
        btn_close = QtWidgets.QPushButton("Close")
        btn_close.setFixedWidth(80)
        btn_close.clicked.connect(dialog.accept)

        bottom_layout = QtWidgets.QHBoxLayout()
        bottom_layout.addStretch()
        bottom_layout.addWidget(btn_close)

        layout.addLayout(bottom_layout)

        dialog.exec_()

    def _extract_fixed_axis(self, obj):
        """Extract axis and origin from a Fixed joint"""
        
        # Fixed joints don't have an axis, but we can show the connection point
        # Use the placement or reference position
        
        try:
            if hasattr(obj, "Placement"):
                origin = obj.Placement.Base
                axis = App.Vector(0, 0, 1)  # No specific direction for fixed
                return axis, origin
        except:
            pass
        
        try:
            if hasattr(obj, "Reference1"):
                ref = obj.Reference1
                if isinstance(ref, (list, tuple)) and len(ref) > 0:
                    body = ref[0]
                    if isinstance(body, (list, tuple)):
                        body = body[0]
                    if hasattr(body, "Shape"):
                        origin = body.Shape.CenterOfMass
                        return App.Vector(0, 0, 1), origin
        except:
            pass
        
        return App.Vector(0, 0, 1), App.Vector(0, 0, 0)

    def _get_joint_body(self, obj, index):
        """Get the name of a body connected to a joint"""
        try:
            ref_prop = f"Reference{index}"
            if hasattr(obj, ref_prop):
                ref = getattr(obj, ref_prop)
                if isinstance(ref, (list, tuple)) and len(ref) > 0:
                    body = ref[0]
                    if isinstance(body, (list, tuple)):
                        body = body[0]
                    if hasattr(body, "Label"):
                        return body.Label
                    return str(body)
        except:
            pass
        return f"Body {index}"

    def highlightCentreOfMass(self, point):
        self.currentStep = 2

        import pivy.coin as coin

        App.Console.PrintMessage(
            f"Centre of Mass = {point}\n"
        )

        # ------------------------------------------
        # Remove previous COM highlight
        # ------------------------------------------

        try:
            if hasattr(self, "comGraphic"):
                self.view.getSceneGraph().removeChild(
                    self.comGraphic
                )
        except Exception:
            pass

        # ------------------------------------------
        # Root scene graph
        # ------------------------------------------

        root = self.view.getSceneGraph()

        # ------------------------------------------
        # Annotation keeps the COM marker visible
        # above the model
        # ------------------------------------------

        annotation = coin.SoAnnotation()

        # ------------------------------------------
        # Position marker at global COM
        # ------------------------------------------

        transform = coin.SoTransform()

        transform.translation.setValue(
            point.x,
            point.y,
            point.z
        )

        # ------------------------------------------
        # Red COM sphere
        # ------------------------------------------

        material = coin.SoMaterial()

        material.diffuseColor = (
            1.0,
            0.0,
            0.0
        )

        material.emissiveColor = (
            1.0,
            0.0,
            0.0
        )

        # ------------------------------------------
        # Make it clearly visible
        # ------------------------------------------

        sphere = coin.SoSphere()

        sphere.radius = 4.0

        # ------------------------------------------
        # Build graphic
        # ------------------------------------------

        annotation.addChild(transform)
        annotation.addChild(material)
        annotation.addChild(sphere)

        # ------------------------------------------
        # Add to FreeCAD scene
        # ------------------------------------------

        root.addChild(annotation)

        self.comGraphic = annotation

    def load_material_database(self):
        """Loads materials via FreeCAD's Materials Python API (1.0+).
        Distinguishes physical engineering materials from visual/hatch presets."""

        materials = []
        appearance_count = 0

        try:
            manager = Materials.MaterialManager()
        except Exception as e:
            print(f">>> Material DB load error: Could not initialize MaterialManager ({e})")
            return materials

        def extract_density_kg_m3(material):
            """Attempts to read density via Modern 1.0 API, Legacy Dicts, and PropertyObjects.
            Returns (density_float, is_physical_material)"""
        
            def parse_to_kg_m3(val):
                if val is None:
                    return None
                try:
                    # 1. FreeCAD Quantity object
                    if hasattr(val, "getValueAs"):
                        res = val.getValueAs("kg/m^3")
                        return float(res.Value if hasattr(res, "Value") else res)
                
                    # 2. Quantity with .Value property
                    if hasattr(val, "Value") and hasattr(val, "Unit"):
                        q_obj = App.Units.Quantity(str(val))
                        res = q_obj.getValueAs("kg/m^3")
                        return float(res.Value if hasattr(res, "Value") else res)
                
                    # 3. Numeric float/int
                    if isinstance(val, (int, float)):
                        return float(val)
                
                    # 4. String representation (e.g., "7850 kg/m^3" or "2.7e-6 kg/mm^3")
                    if isinstance(val, str) and val.strip():
                        q_obj = App.Units.Quantity(val)
                        res = q_obj.getValueAs("kg/m^3")
                        return float(res.Value if hasattr(res, "Value") else res)
                except Exception:
                    pass
                return None

            # Check Strategy A: Modern FreeCAD 1.0+ API
            try:
                if hasattr(material, "getPhysicalValue"):
                    d = parse_to_kg_m3(material.getPhysicalValue("Density"))
                    if d is not None and d > 0:
                        return d, True
            except Exception:
                pass

            # Check Strategy B: Legacy PhysicalProperties dictionary
            try:
                if hasattr(material, "PhysicalProperties"):
                    props = material.PhysicalProperties
                    if hasattr(props, "get") and props.get("Density"):
                        d = parse_to_kg_m3(props.get("Density"))
                        if d is not None and d > 0:
                            return d, True
            except Exception:
                pass

            # Check Strategy C: Direct key indexing material["Density"]
            try:
                if hasattr(material, "__getitem__"):
                    d = parse_to_kg_m3(material["Density"])
                    if d is not None and d > 0:
                        return d, True
            except Exception:
                pass

            # Check Strategy D: PropertyObjects dictionary
            try:
                if hasattr(material, "PropertyObjects") and "Density" in material.PropertyObjects:
                    p_obj = material.PropertyObjects["Density"]
                    d = parse_to_kg_m3(getattr(p_obj, "Value", p_obj))
                    if d is not None and d > 0:
                        return d, True
            except Exception:
                pass

            return 0.0, False

        try:
            all_materials = manager.Materials
        except Exception as e:
            print(f">>> Material DB load error: {e}")
            return materials

        if hasattr(all_materials, "items"):
            material_iter = list(all_materials.items())
        else:
            material_iter = [(None, m) for m in all_materials]

        def get_path(material, mat_uuid):
            library_root = getattr(material, "LibraryRoot", None)
            directory = getattr(material, "Directory", None)

            if library_root and directory:
                combined = os.path.join(str(library_root), str(directory))
                if os.path.exists(combined):
                    return combined
                if os.path.exists(str(directory)):
                    return str(directory)
                return combined

            if directory:
                return str(directory)
            if library_root:
                return str(library_root)

            return f"uuid:{mat_uuid}" if mat_uuid else "unknown"

        for key, material in material_iter:
            if material is None:
                continue

            mat_name = getattr(material, "Name", None) or (str(key) if key else "Unknown")
            mat_uuid = getattr(material, "UUID", None) or key
            mat_path = get_path(material, mat_uuid)

            density_val, density_ok = extract_density_kg_m3(material)

            if density_ok:
                materials.append({
                    "name": mat_name,
                    "Name": mat_name,
                    "uuid": mat_uuid,
                    "UUID": mat_uuid,
                    "density": density_val,
                    "Density": density_val,
                    "density_reliable": True,
                    "path": mat_path,
                    "Path": mat_path,
                })
            else:
                # Skip non-physical items (Hatch pattern cards, visual appearance presets)
                appearance_count += 1

        print(f">>> Material DB loaded: {len(materials)} physical materials ready. ({appearance_count} visual/hatch presets skipped)")

        return materials

    def run_material_selector(self):
        """Manages the embedded sidebar material selection UI."""
        body = self.movingBody

        # Always reload database to avoid caching empty lists
        self.materials_db = self.load_material_database()

        if not hasattr(self, "mat_container"):
            self.mat_container = QtWidgets.QWidget()
            layout = QtWidgets.QVBoxLayout(self.mat_container)
            layout.setContentsMargins(0, 5, 0, 5)

            lbl_parts = QtWidgets.QLabel("<b>Assembly Parts:</b>")
            self.list_parts = QtWidgets.QListWidget()
            self.list_parts.setMaximumHeight(100)

            lbl_search = QtWidgets.QLabel("<b>Search Material:</b>")
            self.edit_name_search = QtWidgets.QLineEdit()
            self.edit_name_search.setPlaceholderText("Filter by name (Steel, ABS)...")

            density_row = QtWidgets.QHBoxLayout()
            self.spin_density_target = QtWidgets.QDoubleSpinBox()
            self.spin_density_target.setRange(0, 30000)
            self.spin_density_target.setValue(0)  # Default 0 = Any Density
            self.spin_density_target.setSuffix(" kg/m³")
            self.spin_density_target.setSpecialValueText("Any Density")

            self.spin_density_tol = QtWidgets.QDoubleSpinBox()
            self.spin_density_tol.setRange(1, 5000)
            self.spin_density_tol.setValue(200)
            self.spin_density_tol.setPrefix("± ")

            density_row.addWidget(self.spin_density_target, 2)
            density_row.addWidget(self.spin_density_tol, 1)

            self.table_mat = QtWidgets.QTableWidget()
            self.table_mat.setColumnCount(2)
            self.table_mat.setHorizontalHeaderLabels(["Name", "Density"])
            self.table_mat.horizontalHeader().setStretchLastSection(True)
            self.table_mat.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
            self.table_mat.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
            self.table_mat.setMaximumHeight(130)

            self.btn_apply_mat = QtWidgets.QPushButton("Apply Material to Selected Part")

            layout.addWidget(lbl_parts)
            layout.addWidget(self.list_parts)
            layout.addWidget(lbl_search)
            layout.addWidget(self.edit_name_search)
            layout.addLayout(density_row)
            layout.addWidget(self.table_mat)
            layout.addWidget(self.btn_apply_mat)

            # Shows the density that Steps 4-6 will use for the moving part
            self.lbl_density_used = QtWidgets.QLabel()
            self.lbl_density_used.setWordWrap(True)
            layout.addWidget(self.lbl_density_used)

            self.assistantLayout.addWidget(self.mat_container)

            # Signal Callbacks
            def on_sidebar_part_selected(current_item, previous_item=None):
                Gui.Selection.clearSelection()
                if not current_item:
                    return
                doc = App.ActiveDocument
                if doc:
                    obj_name = current_item.data(QtCore.Qt.UserRole)
                    obj = doc.getObject(obj_name)
                    if obj:
                        Gui.Selection.addSelection(obj)

            def filter_sidebar_materials(*args):
                query = self.edit_name_search.text().lower().strip()
                target_density = self.spin_density_target.value()
                tol = self.spin_density_tol.value()

                self.table_mat.setRowCount(0)

                for mat in getattr(self, "materials_db", []):
                    matches_name = (not query) or (query in mat["name"].lower())
                    # Match if density filter is off (0), if density is close, OR if card density is unparsed
                    matches_density = (
                        target_density == 0
                        or mat["density"] == 0.0
                        or abs(mat["density"] - target_density) <= tol
                    )

                    if matches_name and matches_density:
                        row = self.table_mat.rowCount()
                        self.table_mat.insertRow(row)

                        item_name = QtWidgets.QTableWidgetItem(mat["name"])
                        item_name.setData(QtCore.Qt.UserRole, mat["path"])

                        dens_str = f"{mat['density']:.0f}" if mat["density"] > 0 else "N/A"
                        item_density = QtWidgets.QTableWidgetItem(dens_str)
                        item_density.setData(QtCore.Qt.UserRole, float(mat["density"]))

                        self.table_mat.setItem(row, 0, item_name)
                        self.table_mat.setItem(row, 1, item_density)

            def apply_sidebar_material():
                curr_part_item = self.list_parts.currentItem()
                if not curr_part_item:
                    return

                selected_rows = self.table_mat.selectedItems()
                if not selected_rows:
                    return

                card_path = self.table_mat.item(selected_rows[0].row(), 0).data(QtCore.Qt.UserRole)
                mat_name = self.table_mat.item(selected_rows[0].row(), 0).text()
                mat_density = self.table_mat.item(selected_rows[0].row(), 1).data(QtCore.Qt.UserRole)
                mat_density = float(mat_density) if mat_density else 0.0

                doc = App.ActiveDocument
                if not doc:
                    return

                obj_name = curr_part_item.data(QtCore.Qt.UserRole)
                obj = doc.getObject(obj_name)

                if obj:
                    card_data = None
                    if card_path and os.path.exists(card_path):
                        try:
                            import importFCMat
                            card_data = importFCMat.read(card_path)
                        except Exception:
                            try:
                                import Material
                                if hasattr(Material, 'importFCMat'):
                                    card_data = Material.importFCMat(card_path)
                            except Exception:
                                pass

                    if not hasattr(obj, "Material"):
                        try:
                            obj.addProperty("App::PropertyMaterial", "Material", "Base", "Material Card")
                        except Exception:
                            pass

                    if hasattr(obj, "Material"):
                        try:
                            if card_data:
                                card_data = dict(card_data)
                                if mat_density > 0 and not card_data.get("Density"):
                                    card_data["Density"] = f"{mat_density} kg/m^3"
                                obj.Material = card_data
                            else:
                                obj.Material = {"Name": mat_name,
                                                "Density": f"{mat_density} kg/m^3"}
                        except Exception:
                            try:
                                obj.Material = mat_name
                            except Exception:
                                pass

                    # Remember what Step 3 assigned (used by the Excel export)
                    if not hasattr(self, "step3Materials"):
                        self.step3Materials = {}
                    self.step3Materials[obj.Name] = (mat_name, mat_density if mat_density > 0 else None)

                    # The Step 3 choice becomes THE density for the pendulum
                    if self._is_moving_part(obj):
                        if mat_density > 0:
                            self.selectedDensity = mat_density
                            self.selectedMaterialName = mat_name
                        else:
                            QtWidgets.QMessageBox.warning(
                                None, "Material",
                                f"'{mat_name}' has no density value, so it cannot be "
                                "used for the simulation. Choose another material.")
                        self._refreshDensityLabel()

                    doc.recompute()
                    curr_part_item.setText(f"{obj.Label} [{mat_name}]")
                    Gui.Selection.clearSelection()
                    Gui.Selection.addSelection(obj)

            self.list_parts.currentItemChanged.connect(on_sidebar_part_selected)
            self.edit_name_search.textChanged.connect(filter_sidebar_materials)
            self.spin_density_target.valueChanged.connect(filter_sidebar_materials)
            self.spin_density_tol.valueChanged.connect(filter_sidebar_materials)
            self.btn_apply_mat.clicked.connect(apply_sidebar_material)

            self._filter_sidebar_materials = filter_sidebar_materials

        self.mat_container.show()

        # Identifies actual assembly component bodies
        def is_assembly_part(obj):
            # Skip utility/datum objects
            skip_types = ("App::Origin", "App::Plane", "App::Line", "App::Point", "App::Axis", "Sketcher::SketchObject")
            if any(obj.isDerivedFrom(t) for t in skip_types if hasattr(obj, "isDerivedFrom")):
                return False

            type_id = getattr(obj, "TypeId", "")

            # Skip sub-features inside PartDesign bodies (Pad, Pocket, etc.)
            if type_id.startswith("PartDesign::") and type_id != "PartDesign::Body":
                return False

            # Skip top container "Assembly" if it holds sub-parts
            if obj.Label.lower() == "assembly" or type_id == "Assembly::AssemblyObject":
                return False

            # If Body is inside an App::Part (e.g. Body inside Pin), let Pin represent it
            if type_id == "PartDesign::Body":
                for parent in getattr(obj, "InList", []):
                    if parent.TypeId == "App::Part":
                        return False

            # Accept App::Part, PartDesign::Body, or shapes
            if type_id in ("App::Part", "PartDesign::Body") or (hasattr(obj, "Shape") and not obj.Shape.isNull()):
                return True

            return False

        # Populate Assembly Parts List
        self.list_parts.clear()
        doc = App.ActiveDocument
        if doc:
            target_row = 0
            row_counter = 0

            for obj in doc.Objects:
                if not is_assembly_part(obj):
                    continue

                # Show the material however it was assigned (Step 3 or
                # elsewhere in FreeCAD), never just "Assigned"
                current_mat = _material_name_of(obj) or "No material"

                item = QtWidgets.QListWidgetItem(f"{obj.Label} [{current_mat}]")
                item.setData(QtCore.Qt.UserRole, obj.Name)
                self.list_parts.addItem(item)

                if body and obj.Name == body.Name:
                    target_row = row_counter

                row_counter += 1

            if self.list_parts.count() > 0:
                self.list_parts.setCurrentRow(target_row)

        self._filter_sidebar_materials()
        self._refreshDensityLabel()

    def showInitialBodyState(self):

        self.currentStep = 2

        App.Console.PrintMessage("\n=== Initial Body State ===\n")

        # --------------------------------------------------
        # Get the moving body
        # --------------------------------------------------

        body = self.movingBody

        App.Console.PrintMessage(
            f"Moving Body = {body.Name}\n"
        )

        # --------------------------------------------------
        # Calculate GLOBAL centre of mass
        # --------------------------------------------------

        # --------------------------------------------------
        # Calculate centre of mass
        # --------------------------------------------------

        shape = body.Shape

        globalCOM = None

        try:
            # Try the actual Body shape first
            globalCOM = shape.CenterOfMass

            App.Console.PrintMessage(
                f"Body Shape COM = {globalCOM}\n"
            )

        except Exception:

            # Body.Shape may be a Compound.
            # Calculate the COM from all solids.
            if hasattr(shape, "Solids") and len(shape.Solids) > 0:

                totalVolume = 0.0
                weightedCOM = App.Vector(0, 0, 0)

                for solid in shape.Solids:

                    volume = solid.Volume
                    com = solid.CenterOfMass

                    weightedCOM += com * volume
                    totalVolume += volume

                if totalVolume > 0:

                    globalCOM = weightedCOM / totalVolume

                    App.Console.PrintMessage(
                        f"Calculated Body COM = {globalCOM}\n"
                    )

        if globalCOM is None:

            App.Console.PrintError(
                "Unable to determine centre of mass.\n"
            )

            return
        # FreeCAD uses mm
        # DAP3D uses metres

        r = [
            globalCOM.x / 1000.0,
            globalCOM.y / 1000.0,
            globalCOM.z / 1000.0
        ]

        # --------------------------------------------------
        # Get initial orientation
        # --------------------------------------------------

        q = body.Placement.Rotation.Q

        # FreeCAD:
        # Q = (x, y, z, w)
        #
        # DAP3D:
        # p = (e0, e1, e2, e3)
        # where scalar comes first

        p = [
            q[3],
            q[0],
            q[1],
            q[2]
        ]

        App.Console.PrintMessage(
            f"COM = {globalCOM}\n"
        )

        App.Console.PrintMessage(
            f"R = {r}\n"
        )

        App.Console.PrintMessage(
            f"P = {p}\n"
        )

        # --------------------------------------------------
        # Highlight centre of mass
        # --------------------------------------------------

        self.highlightCentreOfMass(globalCOM)

        # --------------------------------------------------
        # Update Assistant
        # --------------------------------------------------

        # Draw through assistantStep so the heading reads "Step 3 of 6".
        # assistantStep() hides the material selector...
        self.assistantStep(
            3,
            6,
            "Initial Body State",
            f"I identified <b>{body.Label}</b> as the moving body.<br><br>"
            "The first DAP3D input is the body's initial "
            "position and orientation.<br><br>"
            "<b>Centre of Mass</b><br>"
            f"R = [{r[0]:.6f}, {r[1]:.6f}, {r[2]:.6f}] m<br><br>"
            "<b>Euler Parameters</b><br>"
            f"P = [{p[0]:.6f}, {p[1]:.6f}, "
            f"{p[2]:.6f}, {p[3]:.6f}]<br><br>"
            "The highlighted point represents the body's "
            "centre of mass.<br><br>"
            "Assign a material below if needed (it is used for the "
            "mass in the next step).<br><br>"
            "<b>Is this correct?</b>",
        )

        # This is the only place the selector is ever shown.
        self.run_material_selector()

        # Hide Driving Axis buttons
        self.highlightAxisButton.hide()
        self.RecheckButton.hide()

        self.assistantButtonYes.setText("✓ Yes")
        self.assistantButtonNo.setText("↻ Recalculate")
        
        self.assistantButtonYes.show()
        self.assistantButtonNo.show()

        # Remove previous connections
        try:
            self.assistantButtonYes.clicked.disconnect()
        except Exception:
            pass

        try:
            self.assistantButtonNo.clicked.disconnect()
        except Exception:
            pass

        # Connect buttons
        self.assistantButtonYes.clicked.connect(
            self.confirmInitialBodyState
        )

        self.assistantButtonNo.clicked.connect(
            self.recalculateInitialBodyState
        )


    # ------------------------------------------------------------
    # Density chosen in Step 3 = density used everywhere afterwards
    # ------------------------------------------------------------

    def _is_moving_part(self, obj):
        """True if obj is the moving body, the object it links to, or a child of it."""
        body = self.movingBody
        if body is None or obj is None:
            return False
        if obj is body or obj.Name == body.Name:
            return True
        if getattr(body, "LinkedObject", None) is obj:
            return True
        return obj in (getattr(body, "Group", []) or [])

    def _materialInfo(self, body):
        """(material name, material source, density kg/m^3 or None) for a body:
        chosen in Step 3, manually picked (assigned in FreeCAD or a density typed
        in Step 3), or Default when nothing was selected."""
        is_pendulum = body is self.movingBody
        density = (getattr(self, "bodyDensity", None) if is_pendulum else None) or _density_of(body)

        if is_pendulum and getattr(self, "bodyDensitySource", "") == "entered manually in Step 3":
            return "Custom density", "Manually picked (density typed in Step 3)", density

        names = {body.Name}
        linked = getattr(body, "LinkedObject", None)
        if linked is not None:
            names.add(linked.Name)
        names |= {c.Name for c in (getattr(body, "Group", []) or [])}
        step3 = getattr(self, "step3Materials", {})
        for n in names:
            if n in step3:
                name3, density3 = step3[n]
                if is_pendulum:
                    density3 = density            # the value locked in Step 3
                return name3, "Chosen in Step 3", density3 or density

        name = _material_name_of(body)
        if name and name.strip().lower() != "default":
            return name, "Manually picked (assigned in FreeCAD)", density
        return "Default", "Default (nothing selected)", density

    def _currentStep3Density(self):
        """(density kg/m^3, source text) as it stands in Step 3, or (None, None)."""
        if getattr(self, "selectedDensity", None):
            return self.selectedDensity, f"material '{self.selectedMaterialName}' chosen in Step 3"
        if self.movingBody is not None:
            d = _density_of(self.movingBody)
            if d:
                name = _material_name_of(self.movingBody)
                if name and not name.startswith("Unnamed material"):
                    return d, f"material '{name}' already assigned to the part"
                return d, "material already assigned to the part"
        return None, None

    def _refreshDensityLabel(self):
        if not hasattr(self, "lbl_density_used"):
            return
        d, src = self._currentStep3Density()
        if d:
            self.lbl_density_used.setText(
                f"<b>Density used for simulation:</b> {d:.1f} kg/m³<br><i>({src})</i>")
        else:
            self.lbl_density_used.setText(
                "<b>Density used for simulation:</b> none yet – apply a material "
                "to the moving part, or you will be asked for a value.")

    def confirmInitialBodyState(self):

        App.Console.PrintMessage(
            "Initial body state confirmed.\n"
        )

        # ------------------------------------------
        # Fix the density now; Steps 4-6 only read self.bodyDensity
        # ------------------------------------------
        density, source = self._currentStep3Density()
        if density is None:
            density, ok = QtWidgets.QInputDialog.getDouble(
                None,
                "Density",
                f"No material with a density is assigned to {self.movingBody.Label}.\n"
                "Enter the density in kg/m³ (or Cancel and apply a material):",
                7850.0, 1.0, 30000.0, 1,
            )
            if not ok:
                return  # stay on Step 3 so a material can be applied
            source = "entered manually in Step 3"

        self.bodyDensity = density
        self.bodyDensitySource = source
        App.Console.PrintMessage(f"Density locked: {density} kg/m^3 ({source})\n")

        self.assistantButtonYes.hide()
        self.assistantButtonNo.hide()
        self.hideMaterialSelector()

        # ------------------------------------------
        # Move to mass properties
        # ------------------------------------------

        self.showMassProperties()


    def showMassProperties(self):
        """Step 4: mass, COM and inertia of the moving body, in SI units."""
        self.currentStep = 3

        App.Console.PrintMessage("\n=== Mass Properties ===\n")

        body = self.movingBody
        if body is None:
            App.Console.PrintError("No moving body detected.\n")
            return

        # ------------------------------------------
        # Density: ALWAYS the value fixed when Step 3 was confirmed
        # ------------------------------------------
        density = getattr(self, "bodyDensity", None)
        if density is None:
            App.Console.PrintError("No density set - confirm Step 3 first.\n")
            self.showInitialBodyState()
            return

        try:
            mass, com, J = _mass_properties(body, density)
        except Exception as e:
            App.Console.PrintError(f"Mass property calculation failed: {e}\n")
            return

        # Body-fixed frame for DAP3D: origin at COM, orientation = part rotation
        R0 = body.Placement.Rotation
        Jp = _AT_J_A(_rot_matrix(R0), J)

        self.bodyDensity = density
        self.bodyMass = mass
        self.bodyCOM_mm = com
        self.bodyJ_global = J
        self.bodyR0 = R0
        self.bodyJp = Jp
        self.bodyPlacement0 = App.Placement(body.Placement)

        App.Console.PrintMessage(f"Density = {density} kg/m^3\nMass = {mass} kg\n")
        App.Console.PrintMessage(f"COM = {com} mm\nJp (body frame) = {Jp} kg m^2\n")

        rows = "<br>".join(
            "[ " + " &nbsp; ".join(f"{x:.4e}" for x in row) + " ]" for row in Jp
        )

        self.assistantStep(
            4,
            6,
            "Mass Properties",
            f"""
            <b>Moving Body</b><br>{body.Label}<br><br>
            <b>Density</b><br>{density:.1f} kg/m³
            <i>({getattr(self, "bodyDensitySource", "")})</i><br><br>
            <b>Mass</b><br>{mass:.6e} kg<br><br>
            <b>Inertia about COM, body frame (DAP3D Jp)</b><br>{rows}<br>
            <b>Units:</b> kg·m²<br><br>
            <b>Are these mass properties correct?</b>
            """,
        )

        self.assistantButtonYes.show()
        self.assistantButtonNo.show()
        for b in (self.assistantButtonYes, self.assistantButtonNo):
            try:
                b.clicked.disconnect()
            except Exception:
                pass
        self.assistantButtonYes.clicked.connect(self.confirmMassProperties)
        self.assistantButtonNo.clicked.connect(self.recalculateMassProperties)

    def confirmMassProperties(self):
        self.currentStep = 4
        App.Console.PrintMessage("Mass properties confirmed.\n")
        self.assistantButtonYes.hide()
        self.assistantButtonNo.hide()
        # Continue to the joint step (previously the assistant stopped here)
        self.showJointProperties()

    def showJointProperties(self):
        """Step 5: find the Revolute joint that forms the pendulum pivot."""
        self.currentStep = 5

        App.Console.PrintMessage("\n=== Joint Properties ===\n")

        joints = [o for o in self.doc.Objects if getattr(o, "JointType", None) == "Revolute"]
        self.detectedJoints = joints

        if not joints:
            self.assistantStep(
                5,
                6,
                "⚠️ No Revolute Joint Found",
                """
                A pendulum needs one <b>Revolute</b> joint between the
                grounded part and the swinging part.<br><br>
                Create it, then click <b>Recheck joints</b>.
                """,
            )
            self.RecheckButton.setText("Recheck joints")
            try:
                self.RecheckButton.clicked.disconnect()
            except Exception:
                pass
            self.RecheckButton.clicked.connect(self.recheckJoints)
            self.RecheckButton.show()
            return

        # Prefer the revolute joint that references the moving body
        joint = joints[0]
        if self.movingBody is not None:
            for j in joints:
                refs = str(getattr(j, "Reference1", "")) + str(getattr(j, "Reference2", ""))
                if self.movingBody.Name in refs:
                    joint = j
                    break

        axis, pivot = _joint_global_frame(joint)
        if axis is None:
            App.Console.PrintWarning(
                "Falling back to the approximate axis extraction - verify the highlighted axis.\n"
            )
            axis, pivot = self._extract_revolute_axis(joint)
        if axis.Length == 0:
            axis = App.Vector(0, 0, 1)
        axis.normalize()

        self.pendulumAxis = axis
        self.pendulumPivot_mm = pivot

        body1 = self._get_joint_body(joint, 1)
        body2 = self._get_joint_body(joint, 2)
        moving_body_name = self.movingBody.Label if self.movingBody else "Unknown"

        L = (self.bodyCOM_mm - pivot).Length if hasattr(self, "bodyCOM_mm") else 0.0

        self.assistantStep(
            5,
            6,
            "Pendulum Pivot",
            f"""
            <b>Joint:</b> {joint.Label} (Revolute)<br><br>
            <b>Axis (global):</b> [{axis.x:.4f}, {axis.y:.4f}, {axis.z:.4f}]<br>
            <b>Pivot (global):</b> [{pivot.x:.3f}, {pivot.y:.3f}, {pivot.z:.3f}] mm<br>
            <b>Pivot → COM distance:</b> {L:.3f} mm<br><br>
            <b>Connected:</b> {body1} ↔ {body2}<br>
            <b>Swinging body:</b> {moving_body_name}<br><br>
            <b>Is this information correct?</b>
            """,
        )

        self.jointParams = {
            "joint": joint,
            "joint_type": "Revolute",
            "axis": axis,
            "position": pivot,
            "body1": body1,
            "body2": body2,
            "moving_body": moving_body_name,
        }

        self.assistantButtonYes.show()
        self.assistantButtonNo.show()
        for b in (self.assistantButtonYes, self.assistantButtonNo):
            try:
                b.clicked.disconnect()
            except Exception:
                pass
        self.assistantButtonYes.clicked.connect(self.confirmJointProperties)
        self.assistantButtonNo.clicked.connect(self.recalculateJointProperties)

        if hasattr(self, "skipButton"):
            self.skipButton.hide()

    def recheckJoints(self):
        """Recheck joints when none were found"""
        
        App.Console.PrintMessage("Rechecking joints...\n")
        
        self.assistantStatus.setText(
            "<b>Step 5 of 6</b><br><br>"
            "⏳ Rechecking for joints..."
        )
        
        QtWidgets.QApplication.processEvents()
        
        # Call showJointProperties again
        self.showJointProperties()

    def skipJointStep(self):
        """Skip joint detection and proceed with manual input"""
        
        App.Console.PrintMessage("Skipping joint detection...\n")
        
        if hasattr(self, 'skipButton'):
            self.skipButton.hide()
        
        # Ask user for manual joint input
        dialog = JointManualInputDialog(self.assembly)
        if dialog.exec_():
            # Store manual joint parameters
            self.jointParams = {
                'joint': None,
                'joint_type': 'Manual Input',
                'axis': dialog.axis,
                'position': dialog.position,
                'body1': dialog.body1,
                'body2': dialog.body2,
                'moving_body': dialog.moving_body
            }
            
            self.confirmJointProperties()

    def confirmJointProperties(self):
        """Step 5 confirmed – proceed to Step 6"""
        
        App.Console.PrintMessage("Joint properties confirmed.\n")
        
        self.assistantButtonYes.hide()
        self.assistantButtonNo.hide()
        
        # Hide any skip button
        if hasattr(self, 'skipButton'):
            self.skipButton.hide()
        
        # Move to Step 6
        self.finalizeAssistant()

    def recalculateJointProperties(self):
        """Recalculate joint properties"""
        
        App.Console.PrintMessage("Recalculating joint properties...\n")
        
        self.assistantButtonYes.hide()
        self.assistantButtonNo.hide()
        
        self.assistantStatus.setText(
            "<b>Step 5 of 6</b><br><br>"
            "⏳ Recalculating joint properties..."
        )
        
        QtWidgets.QApplication.processEvents()
        
        # Re-run joint detection
        self.showJointProperties()

    def finalizeAssistant(self):
        """Step 6: build DAP3D input files and offer the ways to run the pendulum."""
        self.currentStep = 6
        App.Console.PrintMessage("\n=== Finalizing Assistant ===\n")

        self.dap3dInputs = {
            "inBodies": self.generateInBodies(),
            "inPoints": self.generateInPoints(),
            "inVectors1": self.generateInVectors1(),
            "inVectors2": self.generateInVectors2(),
            "inJoints": self.generateInJoints(),
            "inForces": self.generateInForces(),
            "inFuncts": self.generateInFuncts(),
            "inAnimate": self.generateInAnimate(),
        }

        self.assistantStep(
            6,
            6,
            "✅ Pendulum Ready",
            f"""
            <b>Swinging body:</b> {self.movingBody.Label}<br>
            <b>Mass:</b> {self.bodyMass:.6e} kg<br>
            <b>Joint:</b> {self.jointParams['joint'].Label}<br><br>
            • <b>Run </b> – solves the equation of motion in
              FreeCAD and animates the part.<br>
            • <b>Export Results (Excel)</b> – saves the pendulum's properties
              and the time history of the last run.<br>
            • <b>Export DAP3D Model</b> – writes the in*.m files for dap.m
              (optional, for cross-checking in MATLAB).<br><br>
            Choose the gravity direction, end time and reporting time step in
            <b>Simulation Settings</b>. The magenta arrow in the 3D view
            shows gravity acting at the centre of mass.
            """,
        )

        if not hasattr(self, "simSettingsGroup"):
            self._buildSimSettings()      # created once, placed above the buttons
        self._setReleaseAngleFromPose()   # default: where the pendulum is drawn
        self.simSettingsGroup.show()

        if not hasattr(self, "pendulumButtons"):
            self.pendulumButtons = []
            for text, slot in (
                ("▶ Run Pendulum", self.runPendulumDynamics),
                ("⏹ Stop Pendulum", self.stopPendulum),
                ("📊 Export Results (Excel)", self.exportResultsExcel),
                ("💾 Export DAP3D Model", self.exportDap3dModel),
            ):
                btn = QtWidgets.QPushButton(text)
                btn.clicked.connect(slot)
                self.assistantLayout.addWidget(btn)
                self.pendulumButtons.append(btn)
        self.runPendulumButton = self.pendulumButtons[0]
        for btn in self.pendulumButtons:
            btn.show()
        self._pendulumControlsShown = True

        self._drawGravityArrow()
        self._drawDriverGlyph()
        self._updateSettingsInfo()

    # ============================================================
    # STEP 6: SIMULATION SETTINGS (gravity direction, end time, time step)
    # ============================================================

    def _gravity(self):
        """Gravity vector in m/s^2 currently chosen by the user (global x, y, z)."""
        g = getattr(self, "gravityVector", None)
        return list(g) if g else list(GRAVITY_VECTOR)

    @staticmethod
    def _mkSpin(lo, hi, val, decimals, step, prefix="", suffix=""):
        s = QtWidgets.QDoubleSpinBox()
        s.setRange(lo, hi)
        s.setDecimals(decimals)
        s.setSingleStep(step)
        s.setValue(val)
        s.setPrefix(prefix)
        s.setSuffix(suffix)
        return s

    def _buildSimSettings(self):
        """Create the Step 6 settings panel once and add it to the assistant."""
        self.simSettingsGroup = QtWidgets.QGroupBox("Simulation Settings")
        form = QtWidgets.QFormLayout(self.simSettingsGroup)

        # ---- Gravity direction --------------------------------
        self.combo_gdir = QtWidgets.QComboBox()
        for label, _ in GRAVITY_PRESETS:
            self.combo_gdir.addItem(label)
        form.addRow("Gravity direction:", self.combo_gdir)

        custom_row = QtWidgets.QHBoxLayout()
        self.spin_gx = self._mkSpin(-1000, 1000, 0.0, 3, 0.1, "x ")
        self.spin_gy = self._mkSpin(-1000, 1000, 0.0, 3, 0.1, "y ")
        self.spin_gz = self._mkSpin(-1000, 1000, -1.0, 3, 0.1, "z ")
        for s in (self.spin_gx, self.spin_gy, self.spin_gz):
            s.setEnabled(False)
            custom_row.addWidget(s)
        form.addRow("Custom direction:", custom_row)

        form.addRow("Gravity magnitude:", QtWidgets.QLabel(f"{GRAVITY_MAGNITUDE} m/s² (fixed)"))

        # ---- Time settings ------------------------------------
        try:
            t_end0 = float(self.simFeaturePy.bTimeEnd.Value)
            dt0 = float(self.simFeaturePy.cTimeStepOutput.Value)
        except Exception:
            t_end0, dt0 = 5.0, 0.02
        if t_end0 <= 0:
            t_end0 = 5.0
        if dt0 <= 0:
            dt0 = 0.02

        self.spin_tend = self._mkSpin(0.001, 3600.0, t_end0, 3, 0.5, suffix=" s")
        self.spin_dt = self._mkSpin(0.0001, 10.0, dt0, 4, 0.005, suffix=" s")
        form.addRow("End time:", self.spin_tend)
        form.addRow("Reporting time step:", self.spin_dt)

        self.spin_theta0 = self._mkSpin(-360.0, 360.0, 30.0, 2, 1.0, suffix=" °")
        self.spin_theta0.setToolTip("Start angle from the vertical (0° = hanging straight "
                                    "down); positive = right-hand rule about the joint axis. "
                                    "The part in the 3D view moves to this angle.")
        form.addRow("Release angle (from vertical):", self.spin_theta0)
        self.spin_theta0.valueChanged.connect(lambda *a: self._resetPendulumPose())

        # ---- External force: one at a time, chosen from the list ----
        form.addRow(QtWidgets.QLabel("<b>External forces</b>"))
        self.combo_driver = QtWidgets.QComboBox()
        for label, _ in DRIVER_TYPES:
            self.combo_driver.addItem(label)
        form.addRow("External force:", self.combo_driver)

        # Constant torque about the joint axis
        self.spin_torque = self._mkSpin(-1.0e6, 1.0e6, 0.5, 4, 0.1, suffix=" N·m")
        self.spin_torque.setToolTip("Positive = right-hand rule about the joint axis "
                                    "(the same sense as the release angle).")
        form.addRow("Torque:", self.spin_torque)

        # Constant force at the centre of mass
        self.spin_force = [self._mkSpin(-1.0e6, 1.0e6, v, 3, 1.0, p, " N")
                           for v, p in ((5.0, "x "), (0.0, "y "), (0.0, "z "))]
        self.row_force = self._rowWidget(self.spin_force)
        self.row_force.setToolTip("Force at the centre of mass, global x, y, z. It keeps "
                                  "the same direction however the pendulum swings.")
        form.addRow("Force:", self.row_force)

        self.driverForm = form
        self.driverRows = {
            "torque": [self.spin_torque],
            "force": [self.row_force],
        }
        self.combo_driver.currentIndexChanged.connect(lambda *a: self._onDriverChanged())
        for widgets in self.driverRows.values():
            for w in widgets:
                for s in (w.spins if hasattr(w, "spins") else [w]):
                    if hasattr(s, "currentIndexChanged"):        # the direction combo
                        s.currentIndexChanged.connect(lambda *a: self._onDriverChanged())
                    else:                                         # spin boxes
                        s.valueChanged.connect(lambda *a: self._onDriverChanged())

        self.lbl_settings_info = QtWidgets.QLabel()
        self.lbl_settings_info.setWordWrap(True)
        form.addRow(self.lbl_settings_info)

        # Feedback from the Step 6 buttons (replaces pop-up messages)
        self.lbl_status = QtWidgets.QLabel()
        self.lbl_status.setWordWrap(True)
        self.lbl_status.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        form.addRow(self.lbl_status)

        self.simEndTime = t_end0
        self.simTimeStep = dt0
        self.gravityVector = list(GRAVITY_VECTOR)

        self.combo_gdir.currentIndexChanged.connect(self._onGravityChanged)
        for s in (self.spin_gx, self.spin_gy, self.spin_gz):
            s.valueChanged.connect(self._onGravityChanged)
        self.spin_tend.valueChanged.connect(self._onTimeChanged)
        self.spin_dt.valueChanged.connect(self._onTimeChanged)

        self.assistantLayout.addWidget(self.simSettingsGroup)
        self._showDriverRows()

    def _setReleaseAngleFromPose(self):
        """Set the release angle to where the pendulum is drawn in the model
        (its current position, e.g. as set in Step 1), measured from the vertical.
        Leaves the value unchanged if the hanging direction is undefined."""
        if not hasattr(self, "spin_theta0"):
            return
        try:
            theta_eq = self._pendulumGeometryCheck()["theta_eq"]
        except Exception:
            return
        if theta_eq is None:
            return
        angle = (-theta_eq + 180.0) % 360.0 - 180.0      # in (-180, 180]
        if angle == -180.0:
            angle = 180.0
        self.spin_theta0.setValue(round(angle, 2))

    def _releasePlacement(self):
        """Placement of the part at the release angle: the CAD pose (Step 6
        entry) turned about the joint axis through the pivot, exactly as the
        solver's start pose. None if it cannot be worked out yet."""
        if not (hasattr(self, "spin_theta0") and hasattr(self, "bodyPlacement0")
                and hasattr(self, "pendulumPivot_mm") and hasattr(self, "pendulumAxis")):
            return None
        try:
            theta_eq = self._pendulumGeometryCheck()["theta_eq"]
        except Exception:
            return None
        if theta_eq is None:
            return None
        th_cad = self.spin_theta0.value() + theta_eq          # from the CAD pose
        o = self.pendulumPivot_mm
        return (App.Placement(o, App.Rotation(self.pendulumAxis, th_cad))
                * App.Placement(-o, App.Rotation())
                * self.bodyPlacement0)

    def _currentPlacement(self):
        """Where the part is shown now (release pose, or the CAD pose)."""
        pl = self._releasePlacement()
        return pl if pl is not None else getattr(self, "bodyPlacement0", None)

    # ------------------------------------------------------------
    # Force driver settings
    # ------------------------------------------------------------

    @staticmethod
    def _rowWidget(spins):
        """Several spin boxes side by side in one form row."""
        w = QtWidgets.QWidget()
        lay = QtWidgets.QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        for s in spins:
            lay.addWidget(s)
        w.spins = spins
        return w

    def _driverType(self):
        """Key of the chosen driver (None, 'torque' or 'force')."""
        if not hasattr(self, "combo_driver"):
            return None
        return DRIVER_TYPES[self.combo_driver.currentIndex()][1]

    def _forceDrivers(self):
        """The chosen force driver in SI units (global axes), or None for a free swing."""
        typ = self._driverType()
        if typ == "torque":
            return {"torque": self.spin_torque.value()}
        if typ == "force":
            return {"force": {"F": [s.value() for s in self.spin_force]}}
        return None

    # ------------------------------------------------------------
    # Driver settings
    # ------------------------------------------------------------

    def _showDriverRows(self):
        """Show only the inputs of the chosen driver."""
        if not hasattr(self, "driverRows"):
            return
        typ = self._driverType()
        for key, widgets in self.driverRows.items():
            for w in widgets:
                w.setVisible(key == typ)
                lbl = self.driverForm.labelForField(w)
                if lbl is not None:
                    lbl.setVisible(key == typ)

    def _onDriverChanged(self):
        self._showDriverRows()
        self._resetPendulumPose()
        self._drawDriverGlyph()
        self._updateSettingsInfo()

    def _setStatus(self, text, level="info", popup=None):
        """Show feedback in the Step 6 panel and the Report view, and optionally
        as a pop-up: popup = (title, message) or (title, None) to reuse text."""
        colours = {"ok": "#1e8449", "warn": "#b9770e", "error": "#c0392b", "info": "#2c3e50"}
        if hasattr(self, "lbl_status"):
            html = text.replace("\n", "<br>")
            self.lbl_status.setText(f"<span style='color:{colours.get(level, '#2c3e50')}'>{html}</span>")
        if level == "error":
            App.Console.PrintError(text + "\n")
        elif level == "warn":
            App.Console.PrintWarning(text + "\n")
        else:
            App.Console.PrintMessage(text + "\n")
        if popup:
            title, message = popup
            box = (QtWidgets.QMessageBox.warning if level in ("warn", "error")
                   else QtWidgets.QMessageBox.information)
            box(None, title, message or text)

    def _gravityFromUi(self):
        """Gravity vector (m/s^2) from the panel, or None if the direction is (0,0,0)."""
        preset = GRAVITY_PRESETS[self.combo_gdir.currentIndex()][1]
        if preset is None:
            v = [self.spin_gx.value(), self.spin_gy.value(), self.spin_gz.value()]
        else:
            v = list(preset)
        n = math.sqrt(_dot(v, v))
        if n < 1e-12:
            return None
        return [GRAVITY_MAGNITUDE * x / n for x in v]

    def _onGravityChanged(self, *args):
        custom = GRAVITY_PRESETS[self.combo_gdir.currentIndex()][1] is None
        for s in (self.spin_gx, self.spin_gy, self.spin_gz):
            s.setEnabled(custom)

        # The pendulum stays where it is shown; only "vertical" moves, so the
        # release angle is re-measured from the new vertical.
        th_cad = None                   # shown pose, from the CAD pose
        if hasattr(self, "spin_theta0"):
            try:
                eq_old = self._pendulumGeometryCheck()["theta_eq"]
                if eq_old is not None:
                    th_cad = self.spin_theta0.value() + eq_old
            except Exception:
                pass
        g = self._gravityFromUi()
        self.gravityVector = g          # None = invalid custom direction
        if g and th_cad is not None:
            try:
                eq_new = self._pendulumGeometryCheck()["theta_eq"]
            except Exception:
                eq_new = None
            if eq_new is not None:
                angle = (th_cad - eq_new + 180.0) % 360.0 - 180.0
                self.spin_theta0.setValue(round(180.0 if angle == -180.0 else angle, 2))
        self._resetPendulumPose()
        self._drawGravityArrow()
        self._drawDriverGlyph()          # the torque arrow is drawn from gravity's direction
        self._updateSettingsInfo()

    def _onTimeChanged(self, *args):
        self.simEndTime = self.spin_tend.value()
        self.simTimeStep = self.spin_dt.value()
        # Keep the Simulation object (and the panel's own boxes) in step
        try:
            self.simFeaturePy.bTimeEnd = self.simEndTime
            self.simFeaturePy.cTimeStepOutput = self.simTimeStep
            self.form.TimeEndSpinBox.setProperty("rawValue", self.simEndTime)
            self.form.TimeStepOutputSpinBox.setProperty("rawValue", self.simTimeStep)
        except Exception:
            pass
        self._resetPendulumPose()
        self._updateSettingsInfo()

    def _settingsErrors(self):
        errors = []
        if not getattr(self, "gravityVector", None):
            errors.append("The custom gravity direction cannot be (0, 0, 0).")
        t_end, dt = self.simEndTime, self.simTimeStep
        if dt >= t_end:
            errors.append("The reporting time step must be smaller than the end time.")
        elif t_end / dt > MAX_SIM_FRAMES:
            errors.append(
                f"{int(round(t_end / dt))} reporting time steps is too many (max {MAX_SIM_FRAMES}). "
                "Use a larger reporting time step or a shorter end time."
            )
        return errors

    def _updateSettingsInfo(self):
        if not hasattr(self, "lbl_settings_info"):
            return
        errors = self._settingsErrors()
        if errors:
            self.lbl_settings_info.setText(
                "<span style='color:#c0392b'><b>⚠ " + "<br>⚠ ".join(errors) + "</b></span>")
        else:
            g = self.gravityVector
            n = int(round(self.simEndTime / self.simTimeStep))
            msg = (f"g = [{g[0]:.3f}, {g[1]:.3f}, {g[2]:.3f}] m/s²<br>"
                   f"{n} steps of {self.simTimeStep:g} s, simulating {self.simEndTime:g} s.")
            if hasattr(self, "pendulumAxis"):
                u = [self.pendulumAxis.x, self.pendulumAxis.y, self.pendulumAxis.z]
                g_perp = [g[i] - _dot(u, g) * u[i] for i in range(3)]
                if math.sqrt(_dot(g_perp, g_perp)) < 1e-6 * (math.sqrt(_dot(g, g)) or 1.0):
                    msg += ("<br><span style='color:#b9770e'>Gravity is parallel to the "
                            "joint axis, so it creates no swing torque.</span>")
            self.lbl_settings_info.setText(msg)
        if getattr(self, "runPendulumButton", None) is not None:
            self.runPendulumButton.setEnabled(not errors)

    def _resetPendulumPose(self):
        """Settings changed: stop any animation and show the part at the release
        angle, with the gravity arrow and the external-force symbol on it."""
        self.stopPendulum()
        pl = self._currentPlacement()
        if self.movingBody is not None and pl is not None:
            self.movingBody.Placement = pl
        self._moveGravityArrow(self._comAt(pl))
        self._moveDriverGlyph(pl)

    def _comAt(self, placement):
        """COM (mm, global) when the part is at 'placement'."""
        if placement is None or not hasattr(self, "bodyPlacement0"):
            return getattr(self, "bodyCOM_mm", None)
        local = self.bodyPlacement0.inverse().multVec(self.bodyCOM_mm)
        return placement.multVec(local)

    # ------------------------------------------------------------
    # Gravity arrow in the 3D view
    # ------------------------------------------------------------

    def _removeGravityArrow(self):
        arrow = getattr(self, "gravityArrow", None)
        if arrow is not None:
            try:
                self.view.getSceneGraph().removeChild(arrow)
            except Exception:
                pass
        self.gravityArrow = None
        self.gravityArrowTransform = None

    def _drawGravityArrow(self):
        """Draw a magenta arrow at the moving body's COM pointing along gravity
        (the weight vector), labelled with the magnitude."""
        import pivy.coin as coin

        self._removeGravityArrow()
        g = getattr(self, "gravityVector", None)
        if not g or not hasattr(self, "bodyCOM_mm"):
            return

        n = math.sqrt(_dot(g, g))
        if n == 0.0:
            return
        d = [x / n for x in g]

        L = 0.0
        if hasattr(self, "pendulumPivot_mm"):
            L = (self.bodyCOM_mm - self.pendulumPivot_mm).Length
        length = max(0.8 * L, 30.0)   # mm
        head = 0.2 * length

        root = coin.SoAnnotation()    # always drawn on top of the model

        self.gravityArrowTransform = coin.SoTransform()
        c = self.bodyCOM_mm
        self.gravityArrowTransform.translation.setValue(c.x, c.y, c.z)
        root.addChild(self.gravityArrowTransform)

        mat = coin.SoMaterial()
        mat.diffuseColor = (0.85, 0.1, 0.85)
        mat.emissiveColor = (0.85, 0.1, 0.85)
        root.addChild(mat)

        style = coin.SoDrawStyle()
        style.lineWidth = 4
        root.addChild(style)

        # Shaft
        coords = coin.SoCoordinate3()
        tip_of_shaft = tuple(d[i] * (length - head) for i in range(3))
        coords.point.setValues(0, 2, [(0.0, 0.0, 0.0), tip_of_shaft])
        root.addChild(coords)
        root.addChild(coin.SoLineSet())

        # Head: SoCone points along +Y and is centred on its own origin
        head_sep = coin.SoSeparator()
        ht = coin.SoTransform()
        ht.translation.setValue(*[d[i] * (length - head / 2.0) for i in range(3)])
        ht.rotation.setValue(coin.SbRotation(coin.SbVec3f(0, 1, 0), coin.SbVec3f(*d)))
        cone = coin.SoCone()
        cone.height = head
        cone.bottomRadius = head * 0.4
        head_sep.addChild(ht)
        head_sep.addChild(cone)
        root.addChild(head_sep)

        # Label
        label_sep = coin.SoSeparator()
        lt = coin.SoTranslation()
        lt.translation.setValue(*[d[i] * length * 1.15 for i in range(3)])
        text = coin.SoText2()
        text.string = f"g = {n:.2f} m/s^2"
        label_sep.addChild(lt)
        label_sep.addChild(text)
        root.addChild(label_sep)

        self.view.getSceneGraph().addChild(root)
        self.gravityArrow = root
        self._moveGravityArrow(self._comAt(self._currentPlacement()))

    def _moveGravityArrow(self, com):
        t = getattr(self, "gravityArrowTransform", None)
        if t is not None and com is not None:
            t.translation.setValue(com.x, com.y, com.z)

    # ------------------------------------------------------------
    # Driver symbol in the 3D view (orange; gravity is magenta)
    #   Constant force          arrow at the COM, fixed direction
    #   Constant torque         curved arrow around the joint axis
    # Parts attached to the pendulum are drawn in the CAD pose and moved with
    # the same rigid motion as the part during playback.
    # ------------------------------------------------------------

    DRIVER_COLOUR = (1.0, 0.55, 0.0)

    def _removeDriverGlyph(self):
        glyph = getattr(self, "driverGlyph", None)
        if glyph is not None:
            try:
                self.view.getSceneGraph().removeChild(glyph)
            except Exception:
                pass
        self.driverGlyph = None
        self.driverGlyphCom = None

    @staticmethod
    def _glyphArrow(coin, direction, length):
        """Arrow from the local origin along a unit direction (shaft + cone)."""
        head = 0.2 * length
        sep = coin.SoSeparator()
        coords = coin.SoCoordinate3()
        coords.point.setValues(0, 2, [(0.0, 0.0, 0.0),
                                      tuple(direction[i] * (length - head) for i in range(3))])
        sep.addChild(coords)
        sep.addChild(coin.SoLineSet())
        hs = coin.SoSeparator()
        ht = coin.SoTransform()
        ht.translation.setValue(*[direction[i] * (length - head / 2.0) for i in range(3)])
        ht.rotation.setValue(coin.SbRotation(coin.SbVec3f(0, 1, 0), coin.SbVec3f(*direction)))
        cone = coin.SoCone()
        cone.height = head
        cone.bottomRadius = head * 0.4
        hs.addChild(ht)
        hs.addChild(cone)
        sep.addChild(hs)
        return sep

    @staticmethod
    def _glyphLabel(coin, position, text):
        sep = coin.SoSeparator()
        t = coin.SoTranslation()
        t.translation.setValue(*position)
        txt = coin.SoText2()
        txt.string = text
        sep.addChild(t)
        sep.addChild(txt)
        return sep

    @staticmethod
    def _arcPoints(center, axis, ref, radius, sign, sweep=1.5 * math.pi, n=40):
        """Points of an arc around 'axis' through 'center', starting along 'ref'
        (perpendicular to the axis), turning in the right-hand sense if sign > 0."""
        e1 = ref
        e2 = _cross(axis, e1)
        pts = []
        for k in range(n + 1):
            a = sign * sweep * k / n
            pts.append([center[i] + radius * (math.cos(a) * e1[i] + math.sin(a) * e2[i])
                        for i in range(3)])
        return pts

    def _glyphCurvedArrow(self, coin, sign, radius, label):
        """Curved arrow around the joint axis at the pivot (torque / rotation sense)."""
        o = self.pendulumPivot_mm
        center = [o.x, o.y, o.z]
        u = [self.pendulumAxis.x, self.pendulumAxis.y, self.pendulumAxis.z]
        g = self._gravity()
        ref = [g[i] - _dot(u, g) * u[i] for i in range(3)]
        n = math.sqrt(_dot(ref, ref))
        if n < 1e-12:                                   # gravity along the axis
            ref = _cross(u, [1.0, 0.0, 0.0])
            if _dot(ref, ref) < 1e-12:
                ref = _cross(u, [0.0, 1.0, 0.0])
            n = math.sqrt(_dot(ref, ref))
        ref = [x / n for x in ref]
        sgn = 1.0 if sign >= 0 else -1.0
        pts = self._arcPoints(center, u, ref, radius, sgn)
        sep = coin.SoSeparator()
        coords = coin.SoCoordinate3()
        coords.point.setValues(0, len(pts) - 2, [tuple(p) for p in pts[:-2]])
        sep.addChild(coords)
        sep.addChild(coin.SoLineSet())
        # arrow head at the end, along the tangent
        tip, before = pts[-1], pts[-3]
        tdir = [tip[i] - before[i] for i in range(3)]
        tn = math.sqrt(_dot(tdir, tdir))
        tdir = [x / tn for x in tdir]
        head = 0.35 * radius
        hs = coin.SoSeparator()
        ht = coin.SoTransform()
        ht.translation.setValue(*[tip[i] - tdir[i] * head / 2.0 for i in range(3)])
        ht.rotation.setValue(coin.SbRotation(coin.SbVec3f(0, 1, 0), coin.SbVec3f(*tdir)))
        cone = coin.SoCone()
        cone.height = head
        cone.bottomRadius = head * 0.4
        hs.addChild(ht)
        hs.addChild(cone)
        sep.addChild(hs)
        sep.addChild(self._glyphLabel(coin, [pts[0][i] + 0.25 * radius * ref[i] for i in range(3)],
                                      label))
        return sep

    def _drawDriverGlyph(self):
        """(Re)draw the symbol of the chosen driver in the CAD pose."""
        self._removeDriverGlyph()
        typ = self._driverType()
        if typ is None or not hasattr(self, "bodyCOM_mm") or not hasattr(self, "pendulumPivot_mm"):
            return
        try:
            import pivy.coin as coin
        except Exception:
            return

        c = self.bodyCOM_mm
        L = max((c - self.pendulumPivot_mm).Length, 30.0)   # mm, sets the symbol size
        root = coin.SoAnnotation()                           # always drawn on top
        mat = coin.SoMaterial()
        mat.diffuseColor = self.DRIVER_COLOUR
        mat.emissiveColor = self.DRIVER_COLOUR
        root.addChild(mat)
        style = coin.SoDrawStyle()
        style.lineWidth = 3
        root.addChild(style)

        if typ == "torque":
            T = self.spin_torque.value()
            root.addChild(self._glyphCurvedArrow(coin, T, 0.35 * L, f"T = {T:g} N m"))

        elif typ == "force":
            F = [s.value() for s in self.spin_force]
            n = math.sqrt(_dot(F, F))
            if n > 0.0:
                d = [x / n for x in F]
                self.driverGlyphCom = coin.SoTransform()       # follows the COM
                self.driverGlyphCom.translation.setValue(c.x, c.y, c.z)
                sep = coin.SoSeparator()
                sep.addChild(self.driverGlyphCom)
                length = 0.8 * L
                sep.addChild(self._glyphArrow(coin, d, length))
                sep.addChild(self._glyphLabel(coin, [d[i] * length * 1.15 for i in range(3)],
                                              f"F = {n:g} N"))
                root.addChild(sep)

        self.view.getSceneGraph().addChild(root)
        self.driverGlyph = root
        self._moveDriverGlyph(self._currentPlacement())

    def _moveDriverGlyph(self, placement=None):
        """Move the parts attached to the pendulum to the part's current
        placement (None = the CAD pose)."""
        if getattr(self, "driverGlyph", None) is None or not hasattr(self, "bodyPlacement0"):
            return
        if placement is None:
            placement = self.bodyPlacement0
        M = placement.multiply(self.bodyPlacement0.inverse())   # CAD pose -> now
        com = M.multVec(self.bodyCOM_mm)
        t = getattr(self, "driverGlyphCom", None)
        if t is not None:
            t.translation.setValue(com.x, com.y, com.z)

    # ============================================================
    # PENDULUM: data shared by the Python solver and the DAP3D export
    # ============================================================

    def _pendulum_data(self):
        c = self.bodyCOM_mm
        o = self.pendulumPivot_mm
        u = self.pendulumAxis
        A0 = _rot_matrix(self.bodyR0)
        q = self.bodyR0.Q  # FreeCAD: (x, y, z, w)
        return {
            "mass": self.bodyMass,
            "Jp": self.bodyJp,
            "r": [c.x / 1000.0, c.y / 1000.0, c.z / 1000.0],
            "p": [q[3], q[0], q[1], q[2]],  # DAP3D: (e0, e1, e2, e3)
            "pivot": [o.x / 1000.0, o.y / 1000.0, o.z / 1000.0],
            # pivot expressed in the body frame (xi, eta, zeta), origin at COM
            "s_pivot": _mat_T_vec(A0, [(o.x - c.x) / 1000.0, (o.y - c.y) / 1000.0, (o.z - c.z) / 1000.0]),
            "axis": [u.x, u.y, u.z],
            "axis_body": _mat_T_vec(A0, [u.x, u.y, u.z]),
        }

    # ------------------------------------------------------------
    # DAP3D input-file generators (see the DAP3D manual, Tables 2-17)
    # ------------------------------------------------------------

    def generateInBodies(self, theta0_deg=0.0, theta0_vert_deg=None):
        """inBodies.m. theta0_deg rotates the starting pose about the joint axis
        (through the pivot), so DAP3D starts exactly where the FreeCAD run started."""
        d = self._pendulum_data()
        r, p = d["r"], d["p"]
        if abs(theta0_deg) > 0.0:
            rot = App.Rotation(App.Vector(*d["axis"]), theta0_deg)
            o = self.pendulumPivot_mm
            com = o + rot.multVec(self.bodyCOM_mm - o)                # mm
            r = [com.x / 1000.0, com.y / 1000.0, com.z / 1000.0]
            q = rot.multiply(self.bodyR0).Q                           # (x, y, z, w)
            p = [q[3], q[0], q[1], q[2]]                              # (e0, e1, e2, e3)
        # Body_struct starts M, J and their inverses at eye(3) (1 kg, 1 kg m^2).
        # Write all of them, so DAP3D cannot fall back to those defaults.
        m = d["mass"]
        Jp = d["Jp"]
        A = _A_from_p(p)
        Jg = [[sum(A[i][k] * Jp[k][l] * A[j][l] for k in range(3) for l in range(3))
               for j in range(3)] for i in range(3)]          # J = A Jp A'
        I3 = [[1.0 * (i == j) for j in range(3)] for i in range(3)]
        return f"""function inBodies
    include_global
    Body = Body_struct;

% Pendulum ({self.movingBody.Label}) - generated by FreeCAD
% Start pose: {"" if theta0_vert_deg is None else f"{theta0_vert_deg:g} deg from the vertical (release angle), i.e. "}CAD pose rotated {theta0_deg:g} deg about the joint axis
    B1 = Body;
    B1.mass  = {m:.10g};
    B1.Jp    = {_mmat(Jp)};
    B1.r     = {_mvec(r)};
    B1.p     = {_mvec(p)};

% Mass and inertia derived from the values above. Body_struct's defaults are
% eye(3) (1 kg, 1 kg m^2), so set them explicitly:
    B1.m_inv  = {1.0 / m:.10g};
    B1.M      = {_mmat([[m * x for x in row] for row in I3])};
    B1.M_inv  = {_mmat([[x / m for x in row] for row in I3])};
    B1.Jp_inv = {_mmat(_inv3(Jp))};
    B1.J      = {_mmat(Jg)};
    B1.J_inv  = {_mmat(_inv3(Jg))};
    B1.r_dot = [0;0;0];
    B1.w     = [0;0;0];
    B1.color = 'b';

    Bodies = [B1];
"""

    # ---- Force drivers in the DAP3D export ----------------------------

    def _exportLoads(self):
        """Force drivers for the DAP3D export: the last run's, or the settings'."""
        res = getattr(self, "pendulumResults", None)
        if res:
            return res.get("loads")
        return self._forceDrivers()

    def generateInPoints(self):
        d = self._pendulum_data()
        return f"""function inPoints
    include_global
    Point = Point_struct;

% P1: pivot on the pendulum (body-fixed coordinates, origin at COM)
    P1 = Point;
    P1.Bindex = 1;
    P1.sPp    = {_mvec(d['s_pivot'])};

% P2: the same pivot on the ground (global coordinates)
    P2 = Point;
    P2.Bindex = 0;
    P2.sPp    = {_mvec(d['pivot'])};

    Points = [P1; P2];
"""

    def generateInVectors1(self):
        d = self._pendulum_data()
        return f"""function inVectors1
    include_global
    Vector = Vector1_struct;

% V1: joint axis on the pendulum (body frame)
    V1 = Vector;
    V1.Bindex = 1;
    V1.sp     = {_mvec(d['axis_body'])};

% V2: joint axis on the ground
    V2 = Vector;
    V2.Bindex = 0;
    V2.sp     = {_mvec(d['axis'])};

    Vectors1 = [V1; V2];
"""

    def generateInVectors2(self):
        return """function inVectors2
    include_global
    Vector = Vector2_struct;

    Vectors2 = [];
"""

    def generateInJoints(self):
        return """function inJoints
    include_global
    Joint = Joint_struct;

% Revolute joint: pendulum (i = body 1) to ground (j = body 0)
    J1 = Joint;
    J1.type      = 'rev';
    J1.iPindex   = 1;   % pivot on the pendulum
    J1.jPindex   = 2;   % pivot on the ground (ground must be j)
    J1.iVindex_a = 1;   % axis on the pendulum
    J1.jVindex_a = 2;   % axis on the ground

    Joints = [J1];
"""

    def generateInForces(self):
        """inForces.m: weight plus the force driver."""
        gvec = self._gravity()
        g = math.sqrt(_dot(gvec, gvec))
        wgt = [x / g for x in gvec]
        loads = self._exportLoads() or {}
        axis = self._pendulum_data()["axis"]
        text, names, n = "", ["S1"], 1

        if loads.get("torque") is not None:
            n += 1
            T = loads["torque"]
            text += f"""
% S{n}: constant torque {T:g} N m about the joint axis (moment in x-y-z frame)
    S{n} = Force;
    S{n}.type    = 'n';
    S{n}.iBindex = 1;
    S{n}.n       = {_mvec([T * x for x in axis])};
"""
            names.append(f"S{n}")

        f = loads.get("force")
        if f is not None:
            n += 1
            text += f"""
% S{n}: constant force at the COM, fixed in space (x-y-z frame)
    S{n} = Force;
    S{n}.type    = 'f';
    S{n}.iBindex = 1;
    S{n}.f       = {_mvec(f['F'])};
"""
            names.append(f"S{n}")

        return f"""function inForces
    include_global
    Force = Force_struct;

    S1 = Force;
    S1.type    = 'weight';
    S1.gravity = {g:.10g};
    S1.wgt     = {_mvec(wgt)};
{text}
    Forces = [{"; ".join(names)}];
"""

    def generateInFuncts(self):
        return """function inFuncts
    include_global
    Funct = Funct_struct;

    Functs = [];
"""

    def generateInAnimate(self):
        d = self._pendulum_data()
        L = math.sqrt(sum((a - b) ** 2 for a, b in zip(d["r"], d["pivot"]))) or 0.1
        R = 1.5 * L
        x, y, z = d["pivot"]
        return f"""function inAnimate
    include_global
    Point = Point_struct;

    Points_anim = [];

    xmin = {x - R:.6g}; xmax = {x + R:.6g};
    ymin = {y - R:.6g}; ymax = {y + R:.6g};
    zmin = {z - R:.6g}; zmax = {z + R:.6g};
    AZ = 60; EL = 20;
"""

    def _matlabLoadsInfo(self):
        """freecad_pendulum_info.m lines describing the force drivers."""
        loads = self._exportLoads() or {}
        T = loads.get("torque")
        f = loads.get("force")
        F = f["F"] if f else [0.0, 0.0, 0.0]
        lines = [
            "% External forces (0 = not used)",
            f"pend.forces_desc  = '{_loads_description(loads).replace(chr(39), chr(39) * 2)}';",
            f"pend.torque       = {0.0 if T is None else T:.10g};   % N m about the joint axis ('n')",
            f"pend.force_on     = {1 if f else 0};",
            f"pend.force        = {_mvec(F)};   % N at the COM, x-y-z, fixed in space ('f')",
        ]
        return "\n".join(lines) + "\n"

    def generateMatlabInfo(self, theta0_deg, t_end, dt, gvec):
        """freecad_pendulum_info.m: the pendulum's properties as a MATLAB struct."""
        d = self._pendulum_data()
        body = self.movingBody.Label.replace("'", "''")
        src = str(getattr(self, "bodyDensitySource", "")).replace("'", "''")
        return f"""% freecad_pendulum_info.m  (written by FreeCAD)
% Properties of the pendulum exported with this DAP3D model. SI units, global axes.
pend = struct();
pend.body       = '{body}';
pend.density    = {self.bodyDensity:.10g};      % kg/m^3 ({src})
pend.mass       = {d['mass']:.10g};             % kg
pend.Jp         = {_mmat(d['Jp'])};   % kg m^2, about COM, body frame
pend.com_cad    = {_mvec(d['r'])};    % m, COM in the CAD pose (theta = 0)
pend.pivot      = {_mvec(d['pivot'])};    % m
pend.axis       = {_mvec(d['axis'])};     % joint axis (unit)
pend.gravity    = {_mvec(gvec)};      % m/s^2
pend.theta0_deg = {theta0_deg:.10g};    % release angle from the VERTICAL (hanging position)
pend.t_end      = {t_end:.10g};         % s  (answer to 'Final time = ?')
pend.dt         = {dt:.10g};            % s  (answer to 'Reporting time-step = ?')
{self._matlabLoadsInfo()}"""

    def exportDap3dModel(self):
        models_dir = QtWidgets.QFileDialog.getExistingDirectory(
            None, "Select the DAP3D 'Models' folder"
        )
        if not models_dir:
            return
        default = "Pendulum_" + re.sub(r"\W+", "_", self.movingBody.Label)
        name, ok = QtWidgets.QInputDialog.getText(
            None, "DAP3D model name", "Model folder name:", text=default
        )
        if not ok or not name:
            return
        folder = os.path.join(models_dir, name)
        os.makedirs(folder, exist_ok=True)

        # Match the last FreeCAD run: same release angle, gravity and times
        res = getattr(self, "pendulumResults", None)
        # Start pose: rotate the CAD pose so the body is at the run's release angle
        if res:
            rot0 = res["theta0_cad_deg"]          # rotation from the CAD pose
            theta0_vert = res["theta0_deg"]       # same pose, from the vertical
        else:
            chk = self._pendulumGeometryCheck()
            eq = chk["theta_eq"] if chk["theta_eq"] is not None else 0.0
            theta0_vert = (self.spin_theta0.value() if hasattr(self, "spin_theta0")
                           else -eq)                 # release angle shown in Step 6
            rot0 = theta0_vert + eq                  # from the CAD pose
        t_end = res["t_end"] if res else getattr(self, "simEndTime", 5.0)
        dt = res["dt_out"] if res else getattr(self, "simTimeStep", 0.02)

        self.dap3dInputs["inBodies"] = self.generateInBodies(rot0, theta0_vert)
        self.dap3dInputs["inPoints"] = self.generateInPoints()
        self.dap3dInputs["inVectors2"] = self.generateInVectors2()
        self.dap3dInputs["inForces"] = self.generateInForces()
        self.dap3dInputs["inJoints"] = self.generateInJoints()
        self.dap3dInputs["inFuncts"] = self.generateInFuncts()
        for fname, content in self.dap3dInputs.items():
            with open(os.path.join(folder, fname + ".m"), "w") as f:
                f.write(content)

        # Pendulum properties + a script that turns DAP3D's T, uT into results
        gvec = res.get("gravity", self._gravity()) if res else self._gravity()
        with open(os.path.join(folder, "freecad_pendulum_info.m"), "w") as f:
            f.write(self.generateMatlabInfo(theta0_vert, t_end, dt, gvec))
        with open(os.path.join(folder, "dap3d_pendulum_results.m"), "w") as f:
            f.write(MATLAB_RESULTS_SCRIPT.replace("__MODEL__", name))

        App.Console.PrintMessage(f"DAP3D model written to {folder}\n")
        note = ("" if res else
                "\n(No FreeCAD run yet - the model starts at the CAD pose.)\n")

        # Will DAP3D's pendulum actually move?  Gravity + force-driver torque at the start pose
        d = self._pendulum_data()
        u = d["axis"]
        d0_ = [d["r"][i] - d["pivot"][i] for i in range(3)]
        d_start = _rodrigues(d0_, u, math.radians(rot0))
        tau = _dot(u, _cross(d_start, [d["mass"] * x for x in gvec]))
        loads = self._exportLoads()
        if loads:
            prep = _prepare_loads(loads, d["pivot"], math.radians(rot0), 0.0)
            tau += _applied_loads(prep, u, d0_, math.radians(rot0), 0.0)[0]
            note += f"\nExternal force: {_loads_description(loads)}\n"
        lever = math.sqrt(max(0.0, _dot(d_start, d_start) - _dot(u, d_start) ** 2))
        g_perp = math.sqrt(max(0.0, _dot(gvec, gvec) - _dot(u, gvec) ** 2))
        if abs(tau) <= 1e-6 * d["mass"] * max(lever * g_perp, 1e-12):
            note += ("\n⚠ WARNING: the pendulum starts at rest in an equilibrium position\n"
                     "(gravity + external-force torque about the hinge is zero), so it will\nNOT move in "
                     "DAP3D. Run the pendulum with a non-zero release angle first,\n"
                     "then export the DAP3D model again.\n")
            App.Console.PrintWarning("Exported pendulum starts in equilibrium - it will not move.\n")
        warn = "equilibrium" in note
        self._setStatus(
            f"{'⚠ Starts at rest in equilibrium - it will NOT move. ' if warn else '✓ '}"
            f"DAP3D model '{name}' written. In MATLAB: dap → {name}, y, "
            f"{t_end:g}, {dt:g}, s → then dap3d_pendulum_results",
            "warn" if warn else "ok",
            popup=("DAP3D export",
                   f"Model written to:\n{folder}\n{note}\n"
                   f"In MATLAB run dap and answer:\n"
                   f"  Which folder contains the model?  {name}\n"
                   f"  Correct the initial conditions?   y\n"
                   f"  Final time = ?                    {t_end:g}\n"
                   f"  Reporting time-step = ?           {dt:g}\n"
                   f"  Standard or Penalty method?       s\n\n"
                   f"Then run:  dap3d_pendulum_results\n"
                   f"(shows the DAP3D results and saves {name}_DAP3D_results.xlsx)"))

    # ------------------------------------------------------------
    # Route A: solve the pendulum in Python inside FreeCAD
    # ------------------------------------------------------------

    def _pendulumGeometryCheck(self):
        """Why might the pendulum not swing?  Returns a dict with:
        d_perp_mm  COM distance from the joint axis (mm)
        g_perp     gravity component perpendicular to the axis (m/s^2)
        theta_eq   resting angle relative to the CAD pose (deg), or None
        problem    text explaining why gravity gives no torque, or None"""
        d = self._pendulum_data()
        u = d["axis"]
        g = self._gravity()
        d0 = [d["r"][i] - d["pivot"][i] for i in range(3)]
        d_perp = [d0[i] - _dot(u, d0) * u[i] for i in range(3)]
        g_perp = [g[i] - _dot(u, g) * u[i] for i in range(3)]
        dp = math.sqrt(_dot(d_perp, d_perp))
        gp = math.sqrt(_dot(g_perp, g_perp))

        problem = None
        if dp < 1e-4:   # < 0.1 mm
            problem = (
                f"The joint axis passes through the centre of mass "
                f"(COM is only {dp * 1000:.3f} mm from the axis), so gravity "
                "cannot turn the part. Check the pivot shown in Step 5: the "
                "Revolute joint must be at the hinge, away from the COM."
            )
        elif gp < 1e-6:
            problem = (
                "Gravity points along the joint axis, so it creates no swing "
                "torque. Choose a different gravity direction in Simulation Settings."
            )
        theta_eq = None
        if problem is None:
            theta_eq = math.degrees(math.atan2(_dot(u, _cross(d_perp, g_perp)),
                                               _dot(d_perp, g_perp)))
        return {"d_perp_mm": dp * 1000.0, "g_perp": gp,
                "theta_eq": theta_eq, "problem": problem}

    def runPendulumDynamics(self):
        # ---- Can this pendulum swing at all? --------------------------
        chk = self._pendulumGeometryCheck()
        if chk["problem"]:
            self._setStatus("Pendulum will not swing: " + chk["problem"], "error",
                            popup=("Pendulum will not swing", chk["problem"]))
            return


        # Angles shown to the user are measured from the VERTICAL: the hanging
        # (rest) position, i.e. gravity projected into the swing plane.
        # The solver works relative to the CAD pose:  theta_cad = theta_vert + theta_eq
        theta_eq = chk["theta_eq"]          # rest position relative to the CAD pose
        cad_from_vertical = -theta_eq       # where the part is drawn, from vertical
        theta0_deg = self.spin_theta0.value() if hasattr(self, "spin_theta0") else 30.0
        loads_ui = self._forceDrivers()     # None = no force driver
        if loads_ui is None and abs(theta0_deg) < 0.01:
            self._setStatus("0° is the hanging (rest) position, so the pendulum will not "
                            "move. Set a non-zero release angle, e.g. 30°.", "warn",
                            popup=("Pendulum at rest", None))
            return
        theta0_cad = theta0_deg + theta_eq  # same pose, measured from the CAD pose
        damping = 0.0  # no damping in this version (the solver still supports it)

        errors = self._settingsErrors() if hasattr(self, "simEndTime") else []
        if errors:
            self._setStatus("\n".join(errors), "error",
                            popup=("Simulation Settings", None))
            return
        t_end = float(getattr(self, "simEndTime", self.simFeaturePy.bTimeEnd.Value))
        dt_out = float(getattr(self, "simTimeStep", self.simFeaturePy.cTimeStepOutput.Value))
        gvec = self._gravity()

        d = self._pendulum_data()
        d0 = [d["r"][i] - d["pivot"][i] for i in range(3)]
        # Force drivers, relative to the pivot; potentials are zero when hanging
        loads = _prepare_loads(loads_ui, d["pivot"], math.radians(theta0_cad),
                               math.radians(theta_eq))
        # Integrate the equation of motion (gravity + force driver)
        times, thetas, omegas, J_O = _integrate_pendulum(
            d["mass"], self.bodyJ_global, d["axis"], d0, gvec,
            damping, math.radians(theta0_cad), 0.0, t_end, dt_out, loads=loads,
        )

        # Small-angle period, useful as a sanity check
        u = d["axis"]
        d_perp = [d0[i] - _dot(u, d0) * u[i] for i in range(3)]
        g_perp = [gvec[i] - _dot(u, gvec) * u[i] for i in range(3)]
        k = d["mass"] * math.sqrt(_dot(d_perp, d_perp)) * math.sqrt(_dot(g_perp, g_perp))
        period = 2 * math.pi * math.sqrt(J_O / k) if k > 0 else float("nan")

        swing = math.degrees(max(thetas) - min(thetas))
        App.Console.PrintMessage(
            f"Animating part      : {self.movingBody.Label}\n"
            f"COM distance to axis: {chk['d_perp_mm']:.3f} mm\n"
            f"CAD pose            : {cad_from_vertical:.2f} deg from vertical\n"
            f"Released at         : {theta0_deg:.2f} deg from vertical\n"
            f"External force      : {_loads_description(loads_ui)}\n"
            f"Swing range         : {swing:.3f} deg\n"
            f"J about pivot axis = {J_O:.6e} kg m^2, small-angle period = {period:.4f} s\n"
        )
        App.Console.PrintMessage("   t [s]   theta from vertical [deg]   omega [rad/s]\n")
        step = max(1, len(times) // 20)
        for t, th, om in list(zip(times, thetas, omegas))[::step]:
            App.Console.PrintMessage(
                f"{t:8.3f} {math.degrees(th) - theta_eq:20.4f} {om:18.5f}\n")

        self.pendulumResults = {
            "t": times, "theta": thetas, "omega": omegas,
            "theta0_deg": theta0_deg,          # from the vertical
            "theta0_cad_deg": theta0_cad,      # from the CAD pose (solver start)
            "theta_eq_deg": theta_eq,          # rest position, from the CAD pose
            "J_O": J_O, "period": period, "d0": d0,
            "t_end": t_end, "dt_out": dt_out, "gravity": gvec,
            "loads": loads_ui,                 # force drivers as set (None = none)
            "loads_prep": loads,               # same, in solver form
        }

        # Placement of the body for each angle: rotate the CAD pose about the pivot axis
        o = self.pendulumPivot_mm
        P0 = self.bodyPlacement0
        axisV = App.Vector(*d["axis"])
        placements = [
            App.Placement(o, App.Rotation(axisV, math.degrees(th)))
            * App.Placement(-o, App.Rotation())
            * P0
            for th in thetas
        ]
        self._playPlacements(times, placements)
        forces = "" if loads_ui is None else f" External force: {_loads_description(loads_ui)}."
        self._setStatus(
            f"✓ Simulated {t_end:g} s from {theta0_deg:g}° (part drawn at "
            f"{cad_from_vertical:.1f}° from vertical). Small-angle period "
            f"{'(gravity only) ' if loads_ui else ''}{period:.4f} s.{forces}",
            "ok")

    # ------------------------------------------------------------
    # Export: pendulum properties + simulation time history (Excel)
    # ------------------------------------------------------------

    def _assemblyBodyRows(self):
        """One row per body in the assembly: role, material and mass properties.
        Positions in m, inertia about each body's COM in global axes (kg m^2)."""
        headers = [
            "Body", "Internal name", "Role", "Material",
            "Density [kg/m^3]", "Volume [m^3]", "Mass [kg]",
            "COM x [m]", "COM y [m]", "COM z [m]",
            "Position x [m]", "Position y [m]", "Position z [m]",
            "Rotation angle [deg]", "Rotation axis x", "Rotation axis y", "Rotation axis z",
            "Jxx [kg m^2]", "Jyy [kg m^2]", "Jzz [kg m^2]",
            "Jxy [kg m^2]", "Jxz [kg m^2]", "Jyz [kg m^2]",
        ]
        rows = [headers]
        bodies = list(getattr(self, "assemblyBodies", []) or [])
        if self.movingBody is not None and self.movingBody not in bodies:
            bodies.append(self.movingBody)
        grounded = list(getattr(self, "groundedBodies", []) or [])
        if self.groundedBody is not None and self.groundedBody not in grounded:
            grounded.append(self.groundedBody)

        for b in bodies:
            if b is self.movingBody:
                role = "Moving (pendulum)"
            elif b in grounded:
                role = "Grounded"
            else:
                role = "Moving (not simulated)"
            mat_name, _, density = self._materialInfo(b)

            row = [b.Label, b.Name, role, mat_name, density] + [None] * (len(headers) - 5)
            try:
                solids = _global_solids(b)
                vol = sum(sol.Volume for sol in solids)          # mm^3
                com = App.Vector(0, 0, 0)
                for sol in solids:
                    com += sol.CenterOfMass * sol.Volume
                com = com * (1.0 / vol)
                row[5] = vol * 1e-9                               # m^3
                row[7:10] = [com.x / 1000.0, com.y / 1000.0, com.z / 1000.0]
                if density:
                    mass, _, J = _mass_properties(b, density)
                    row[6] = mass
                    row[17:23] = [J[0][0], J[1][1], J[2][2], J[0][1], J[0][2], J[1][2]]
            except Exception as e:
                App.Console.PrintWarning(f"No mass properties for {b.Label}: {e}\n")
            try:
                plc = b.getGlobalPlacement() if hasattr(b, "getGlobalPlacement") else b.Placement
            except Exception:
                plc = b.Placement
            ax = plc.Rotation.Axis
            row[10:17] = [plc.Base.x / 1000.0, plc.Base.y / 1000.0, plc.Base.z / 1000.0,
                          math.degrees(plc.Rotation.Angle), ax.x, ax.y, ax.z]
            rows.append(row)
        return rows

    @staticmethod
    def _loadsPropertyRows(loads):
        """Properties-sheet rows (name, values, unit) describing the force driver."""
        if not loads:
            return [("External force", ["None"], "")]
        rows = []
        if loads.get("torque") is not None:
            rows.append(("Constant torque about joint axis", [loads["torque"]], "N m"))
        f = loads.get("force")
        if f is not None:
            rows.append(("Constant force at COM, fixed in space (x;y;z)", f["F"], "N"))
        return rows

    def exportResultsExcel(self):
        """Save the run as an Excel workbook (.xlsx): Properties, Bodies and Results
        sheets, every value in its own cell whatever the regional settings."""
        res = getattr(self, "pendulumResults", None)
        if not res:
            self._setStatus("Run the pendulum first, then export the results.", "warn",
                            popup=("Export results", None))
            return

        default = "Pendulum_" + re.sub(r"\W+", "_", self.movingBody.Label) + "_results.xlsx"
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            None, "Save pendulum results", default, "Excel workbook (*.xlsx)"
        )
        if not path:
            return
        if not path.lower().endswith(".xlsx"):
            path += ".xlsx"

        d = self._pendulum_data()
        m, J_O, u, d0 = d["mass"], res["J_O"], d["axis"], res["d0"]
        pivot = d["pivot"]
        gvec = res.get("gravity", list(GRAVITY_VECTOR))
        joint = self.jointParams["joint"]
        pend_mat, _, _ = self._materialInfo(self.movingBody)

        # ---- Properties sheet ----------------------------------------
        def vec(v):
            return list(v) + [None] * (3 - len(v))

        prop_rows = [["Parameter", "Value / x", "y", "z", "Unit"]]
        for name, vals, unit in [
            ("Body", [self.movingBody.Label], ""),
            ("Joint", [joint.Label], ""),
            ("Joint type", [getattr(joint, "JointType", self.jointParams.get("joint_type", ""))], ""),
            ("Material", [pend_mat], ""),
            ("Density", [self.bodyDensity], "kg/m^3"),
            ("Mass", [m], "kg"),
            ("COM at t=0 (x;y;z)", d["r"], "m"),
            ("Pivot (x;y;z)", pivot, "m"),
            ("Joint axis (x;y;z)", u, "-"),
            ("Pivot to COM distance", [math.sqrt(_dot(d0, d0))], "m"),
            ("Jp row 1 (about COM, body frame)", d["Jp"][0], "kg m^2"),
            ("Jp row 2 (about COM, body frame)", d["Jp"][1], "kg m^2"),
            ("Jp row 3 (about COM, body frame)", d["Jp"][2], "kg m^2"),
            ("J about joint axis (J_O)", [J_O], "kg m^2"),
            ("Gravity vector (x;y;z)", gvec, "m/s^2"),
            ("Release angle (from vertical)", [res["theta0_deg"]], "deg"),
        ] + self._loadsPropertyRows(res.get("loads")) + [
            ("End time", [res["t_end"]], "s"),
            ("Reporting time step", [res["dt_out"]], "s"),
            ("Small-angle period", [res["period"]], "s"),
        ]:
            prop_rows.append([name] + vec(vals) + [unit])
        prop_rows += [[], ["Note", "theta is measured from the vertical (hanging position) "
                                   "about the joint axis; R is the force the pivot applies "
                                   "to the pendulum"]]
        if res.get("loads"):
            prop_rows.append(["Note", "With an external force: R = m*a - m*g - (applied force), "
                                      "and PE includes the potential of the constant torque "
                                      "or constant force (zero when hanging), so E total "
                                      "stays constant"])

        # ---- Results sheet --------------------------------------------
        headers = [
            "t [s]", "theta [deg]", "omega [rad/s]", "alpha [rad/s^2]",
            "COM x [m]", "COM y [m]", "COM z [m]",
            "COM vx [m/s]", "COM vy [m/s]", "COM vz [m/s]",
            "COM ax [m/s^2]", "COM ay [m/s^2]", "COM az [m/s^2]",
            "Rx [N]", "Ry [N]", "Rz [N]", "|R| [N]",
            "KE [J]", "PE [J]", "E total [J]",
        ]
        data = [headers]
        for t, th, om in zip(res["t"], res["theta"], res["omega"]):
            s = _pendulum_state(m, J_O, u, d0, gvec, 0.0, th, om,
                                loads=res.get("loads_prep"))
            com = [pivot[i] + s["d"][i] for i in range(3)]
            R = s["R"]
            data.append(
                [t, math.degrees(th) - res["theta_eq_deg"], om, s["alpha"]]
                + com + s["v"] + s["a"] + R
                + [math.sqrt(_dot(R, R)), s["KE"], s["PE"], s["KE"] + s["PE"]]
            )

        body_rows = self._assemblyBodyRows()

        try:
            _write_xlsx(path, [
                {"name": "Properties", "rows": prop_rows, "bold_rows": {0},
                 "freeze_rows": 1, "widths": [36, 18, 16, 16, 10]},
                {"name": "Bodies", "rows": body_rows, "bold_rows": {0},
                 "freeze_rows": 1, "widths": [18, 16, 22, 22] + [15] * (len(body_rows[0]) - 4)},
                {"name": "Results", "rows": data, "bold_rows": {0},
                 "freeze_rows": 1, "widths": [10] + [15] * (len(headers) - 1)},
            ])
        except Exception as e:
            App.Console.PrintError(f"Could not write {path}: {e}\n")
            self._setStatus(f"Could not save the Excel file: {e}", "error",
                            popup=("Export results", None))
            return

        App.Console.PrintMessage(f"Pendulum results written to {path}\n")
        self._setStatus(f"✓ Results saved to {os.path.basename(path)}", "ok",
                        popup=("Export results", f"Results saved to:\n{path}"))

    # ------------------------------------------------------------
    # Playback
    # ------------------------------------------------------------

    def _playPlacements(self, times, placements):
        self.stopPendulum()
        if not placements:
            return
        dt = times[1] - times[0] if len(times) > 1 else 0.03
        # The screen can't redraw faster than ~60 Hz, so for small time steps
        # show every n-th frame; playback then still runs in real time.
        stride = max(1, int(math.ceil(0.015 / dt)))
        self._pFrames = placements[::stride]
        self._pIndex = 0
        # COM in the part's own coordinates, so the gravity arrow can follow it
        if hasattr(self, "bodyCOM_mm") and hasattr(self, "bodyPlacement0"):
            self._comLocal = self.bodyPlacement0.inverse().multVec(self.bodyCOM_mm)
        if not hasattr(self, "pendulumTimer"):
            self.pendulumTimer = QtCore.QTimer()
            self.pendulumTimer.timeout.connect(self._pendulumTick)
        self.pendulumTimer.setInterval(max(1, int(round(dt * stride * 1000))))
        self.pendulumTimer.start()

    def _pendulumTick(self):
        if not getattr(self, "_pFrames", None) or self.movingBody is None:
            self.stopPendulum()
            return
        pl = self._pFrames[self._pIndex]
        self.movingBody.Placement = pl
        if getattr(self, "_comLocal", None) is not None:
            self._moveGravityArrow(pl.multVec(self._comLocal))
        self._moveDriverGlyph(pl)
        self._pIndex = (self._pIndex + 1) % len(self._pFrames)

    def stopPendulum(self):
        if hasattr(self, "pendulumTimer"):
            self.pendulumTimer.stop()

    def recalculateMassProperties(self):

        App.Console.PrintMessage(
            "Recalculating mass properties...\n"
        )

        self.assistantButtonYes.hide()
        self.assistantButtonNo.hide()

        self.assistantStatus.setText(
            "<b>Step 4 of 6</b><br><br>"
            "⏳ Recalculating mass properties..."
        )

        QtWidgets.QApplication.processEvents()

        self.showMassProperties()

    def recalculateInitialBodyState(self):

        App.Console.PrintMessage(
            "Recalculating initial body state...\n"
        )

        self.assistantButtonYes.hide()
        self.assistantButtonNo.hide()

        self.assistantStatus.setText(
            "<b>Step 3 of 6</b><br><br>"
            "⏳ Recalculating the initial body state..."
        )

        QtWidgets.QApplication.processEvents()

        self.showInitialBodyState()    

    def setUiInitialValues(self):
        self.form.TimeStartSpinBox.setProperty("rawValue", self.simFeaturePy.aTimeStart.Value)
        self.form.TimeEndSpinBox.setProperty("rawValue", self.simFeaturePy.bTimeEnd.Value)
        self.form.TimeStepOutputSpinBox.setProperty(
            "rawValue", self.simFeaturePy.cTimeStepOutput.Value
        )
        self.form.GlobalErrorToleranceSpinBox.setProperty(
            "rawValue", self.simFeaturePy.fGlobalErrorTolerance
        )
        self.setFrameValue(0)
        self.form.FramesPerSecondSpinBox.setValue(self.simFeaturePy.jFramesPerSecond)

    def setSpinboxPrecision(self, spinbox, precision, unit=App.Units.TimeSpan):
        q = App.Units.Quantity()
        q.Unit = unit
        q.Format = {"Precision": precision}
        spinbox.setProperty("value", q)

    def accept(self):
        self.deactivate()
        UtilsAssembly.restoreAssemblyPartsPlacements(self.assembly, self.initialPlcs)
        App.closeActiveTransaction()
        return True

    def reject(self):
        self.deactivate()
        App.closeActiveTransaction(True)
        return True

    def deactivate(self):
        self.animationTimer.stop()
        self.stopPendulum()
        self._removeGravityArrow()
        self._removeDriverGlyph()
        self.simFeaturePy.Proxy.setMotionsChangedCallback(None)
        if Gui.Control.activeDialog():
            Gui.Control.closeDialog()

    def onTimeStartChanged(self, quantity):
        self.simFeaturePy.aTimeStart = self.form.TimeStartSpinBox.property("rawValue")

    def onTimeEndChanged(self, quantity):
        self.simFeaturePy.bTimeEnd = self.form.TimeEndSpinBox.property("rawValue")

    def onTimeStepOutputChanged(self, quantity):
        self.simFeaturePy.cTimeStepOutput = self.form.TimeStepOutputSpinBox.property("rawValue")

    def onGlobalErrorToleranceChanged(self, quantity):
        self.simFeaturePy.fGlobalErrorTolerance = self.form.GlobalErrorToleranceSpinBox.property(
            "rawValue"
        )

    def onItemDoubleClicked(self, item):
        row = self.form.motionList.row(item)
        if row < len(self.simFeaturePy.Group):
            motion = self.simFeaturePy.Group[row]
            motion.ViewObject.Proxy.openEditDialog()
            self.onMotionsChanged()

    def createSimulationObject(self):
        sim_group = UtilsAssembly.getSimulationGroup(self.assembly)
        self.simFeaturePy = sim_group.newObject("App::FeaturePython", "Simulation")
        Simulation(self.simFeaturePy)
        ViewProviderSimulation(self.simFeaturePy.ViewObject)

    def createMotionObject(self, motionType, joint, formula):
        motion = self.assembly.newObject("App::FeaturePython", "Motion")
        Motion(motion, motionType, joint, formula)
        ViewProviderMotion(motion.ViewObject)

        listOfMotions = self.simFeaturePy.Group
        listOfMotions.append(motion)
        self.simFeaturePy.Group = listOfMotions

    def onMotionsChanged(self):
        self.form.motionList.clear()
        for motion in self.simFeaturePy.Group:
            self.form.motionList.addItem(motion.Label)

    def runKinematics(self):
        self.assembly.generateSimulation(self.simFeaturePy)
        nFrms = self.assembly.numberOfFrames()
        self.form.frameSlider.setMaximum(nFrms - 1)
        self.setFrameValue(nFrms - 1)
        self.form.groupBox_player.show()

    def onFrameChanged(self, val):
        self.assembly.updateForFrame(val)
        self.form.FrameLabel.setText(translate("Assembly", "Frame" + " " + str(val)))
        time = float(val * self.simFeaturePy.cTimeStepOutput)
        self.form.FrameTimeLabel.setText(f"{time:.2f} s")

    def onFramesPerSecondChanged(self):
        self.simFeaturePy.jFramesPerSecond = self.form.FramesPerSecondSpinBox.value()

    def playBackward(self):
        pass

    def animationTimerStartForward(self):
        self.direction = 1
        self.animationTimerStart()

    def animationTimerStartBackward(self):
        self.direction = -1
        self.animationTimerStart()

    def animationTimerStart(self):
        self.animationTimer.stop()
        self.currentFrm = self.form.frameSlider.value()
        self.startFrm = 1
        self.endFrm = self.form.frameSlider.maximum()
        if self.startFrm >= self.endFrm:
            return

        self.fps = self.simFeaturePy.jFramesPerSecond
        self.deltaTime = 1.0 / self.fps
        self.startTime = time.time()
        self.index = self.currentFrm
        self.animationTimer.setInterval(self.deltaTime * 1000)  # ms
        self.animationTimer.start()

    def playAnimation(self):
        range_ = self.endFrm - self.startFrm
        offset = self.currentFrm - self.startFrm
        count = int((time.time() - self.startTime) / self.deltaTime)
        self.index = ((self.direction * count + offset) % range_) + self.startFrm
        self.setFrameValue(self.index)


    def displayLastFrame(self):
        nFrms = self.assembly.numberOfFrames()
        self.setFrameValue(nFrms - 1)

    def stepBackward(self):
        self.animationTimer.stop()

        nextFrm = self.form.frameSlider.value() - 1
        if nextFrm < 1:
            nextFrm = self.form.frameSlider.maximum()  # wraparound
        self.setFrameValue(nextFrm)

    def stepForward(self):
        self.animationTimer.stop()

        nextFrm = self.form.frameSlider.value() + 1
        if nextFrm > self.form.frameSlider.maximum():
            nextFrm = 1  # wraparound
        self.setFrameValue(nextFrm)

    def setFrameValue(self, val):
        if val < 1:
            val = 1
        if val > self.form.frameSlider.maximum():
            val = self.form.frameSlider.maximum()

        self.form.frameSlider.setValue(val)

    def stopAnimation(self):
        self.animationTimer.stop()

    def goBackStep(self):
        """Go back to the previous step"""
        
        if not hasattr(self, 'currentStep') or self.currentStep <= 0:
            App.Console.PrintMessage("Already at first step.\n")
            return
        
        self.currentStep -= 1
        self.hideMaterialSelector()  # showInitialBodyState re-shows it if we land there
        self.hidePendulumControls()  # finalizeAssistant re-shows them if we land there
        
        App.Console.PrintMessage(f"Going back to Step {self.currentStep}\n")
        
        # Re-display the previous step
        if self.currentStep == 0:
            # Remove the highlighted driving axis
            if hasattr(self, "axisGraphic") and self.axisGraphic is not None:
                try:
                    self.view.getSceneGraph().removeChild(
                        self.axisGraphic
                    )
                    self.axisGraphic = None

                    App.Console.PrintMessage(
                        "Driving axis highlight removed.\n"
                    )

                except Exception as e:
                    App.Console.PrintError(
                        f"Could not remove axis highlight: {e}\n"
                    )
            self.analyseAssembly()
        elif self.currentStep == 1:
            # Remove centre-of-mass highlight
            if hasattr(self, "comGraphic") and self.comGraphic is not None:
                try:
                    self.view.getSceneGraph().removeChild(
                        self.comGraphic
                    )

                    self.comGraphic = None

                    App.Console.PrintMessage(
                        "Centre of mass highlight removed.\n"
                    )

                except Exception as e:
                    App.Console.PrintError(
                        f"Could not remove COM highlight: {e}\n"
                    )
            # Remove Step 3 buttons
            self.assistantButtonYes.hide()
            self.assistantButtonNo.hide()
            self.highlightDrivingAxis()
        elif self.currentStep == 2:
            self.showInitialBodyState()
        elif self.currentStep == 3:
            self.showMassProperties()
        elif self.currentStep == 4:
            self.assistantStatus.setText(
                "<b>Step 4 of 6</b><br><br>"
                "<b>Mass Properties Confirmed ✓</b><br><br>"
                "The body's mass and inertia properties "
                "have been accepted."
            )
        elif self.currentStep == 5:
            self.showJointProperties()
        
        self.updateBackButtonState()

    def updateBackButtonState(self):
        """Enable or disable the back button based on current step"""
        if not hasattr(self, 'currentStep'):
            self.currentStep = 0
        self.backButton.setEnabled(self.currentStep > 0)

    def addMotionClicked(self):
        dialog = MotionEditDialog(self.assembly)
        if dialog.exec_():
            self.createMotionObject(dialog.motionType, dialog.joint, dialog.formula)

    # Taskbox keyboard event handler
    def eventFilter(self, watched, event):
        if self.form is not None and watched == self.form.motionList:
            if event.type() == QtCore.QEvent.ShortcutOverride:
                if event.key() == QtCore.Qt.Key_Delete:
                    event.accept()
                    return True  # Indicate that the event has been handled
                return False

            elif event.type() == QtCore.QEvent.KeyPress:
                if event.key() == QtCore.Qt.Key_Delete:
                    self.deleteSelectedMotions()
                    return True  # Consume the event

        return super().eventFilter(watched, event)

    def deleteSelectedMotions(self):
        selected_indexes = self.form.motionList.selectedIndexes()
        sorted_indexes = sorted(selected_indexes, key=lambda x: x.row(), reverse=True)
        for index in sorted_indexes:
            row = index.row()
            if row < len(self.simFeaturePy.Group):
                motion = self.simFeaturePy.Group[row]
                # First remove the link from the viewObj
                self.simFeaturePy.Group.remove(motion)
                # Delete the object
                motion.Document.removeObject(motion.Name)


if App.GuiUp:
    Gui.addCommand("Assembly_CreateSimulation", CommandCreateSimulation())
