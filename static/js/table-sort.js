/* Column sort for the rows a screen has already rendered.
 *
 * WHY THIS IS A FILE AND NOT TWO COPIES IN TWO TEMPLATES
 * ------------------------------------------------------
 * Patient Records and Medicine Inventory both need exactly this, and this
 * project's rule is that one behaviour lives in one place -- the same argument
 * utils/unavailable.py makes for its shared reasons, and the same one the header
 * search follows by handing its term to Patient Records' existing filter rather
 * than matching anything itself. Two hand-written copies of a comparator is two
 * chances for one screen to sort blanks to the top while the other sorts them to
 * the bottom, and nobody would notice until somebody compared the two screens.
 *
 * Each screen still owns its own column list, because which columns are worth
 * sorting is a question about that screen's table. Only the sorting is shared.
 *
 * WHAT IT SORTS, AND WHAT IT DELIBERATELY DOES NOT TOUCH
 * ------------------------------------------------------
 * It reorders the row elements already in the tbody and nothing else. It does
 * not show or hide anything, so it composes with the search box and the filter
 * panel instead of fighting them: those decide which rows are visible, this
 * decides what order rows sit in, and the two questions never meet. A sort
 * applied while a filter is on therefore sorts what the operator can see -- the
 * hidden rows are reordered too, but they are hidden, so what the table shows is
 * the filtered subset in sorted order. Clearing the filter afterwards reveals the
 * rest already in the same order, which is what "the list is sorted by name"
 * ought to mean.
 *
 * It re-formats nothing and derives nothing. Every value it compares was written
 * into a data-* attribute by the server, in its stored form -- the arrangement
 * Screens 03, 06, 09 and 12 already use for their filters.
 *
 * BLANKS ALWAYS SORT LAST
 * -----------------------
 * In both directions, deliberately. A patient with no recorded visit and a
 * medicine with no expiry date on file are absences, not extreme values: sorting
 * "earliest expiry first" to answer "what do I use up next" must not open with a
 * page of items that have no expiry at all, and reversing the direction must not
 * then bury them. So a missing value is never ranked against a present one -- it
 * is held at the bottom whichever way the column is pointing.
 */
(function (global) {
  'use strict';

  // A stable sort matters here: rows that tie on the chosen column must keep the
  // order the server sent them in, which is alphabetical on both screens. Sorting
  // by status therefore yields status order with names still A-Z inside each
  // group, rather than an arbitrary shuffle that changes between clicks.
  // Array.prototype.sort is stable in every browser this project targets, but the
  // index tiebreak below makes it so regardless of that guarantee.
  function stableSort(items, compare) {
    return items
      .map(function (item, index) { return { item: item, index: index }; })
      .sort(function (a, b) {
        var result = compare(a.item, b.item);
        return result !== 0 ? result : a.index - b.index;
      })
      .map(function (entry) { return entry.item; });
  }

  function readValue(row, column) {
    var raw = row.getAttribute(column.attr);
    if (raw === null) { return null; }
    raw = String(raw).trim();
    if (raw === '') { return null; }

    if (column.type === 'number') {
      var num = parseFloat(raw);
      return isNaN(num) ? null : num;
    }
    // 'date' values are ISO yyyy-mm-dd, which compares correctly as plain text,
    // so they need no Date object and cannot be knocked sideways by a timezone.
    // 'text' values are written lower-cased by the server.
    return raw;
  }

  function comparator(column, direction) {
    var sign = direction === 'desc' ? -1 : 1;
    return function (rowA, rowB) {
      var a = readValue(rowA, column);
      var b = readValue(rowB, column);

      // Absent values are held at the bottom in both directions; see the header.
      if (a === null && b === null) { return 0; }
      if (a === null) { return 1; }
      if (b === null) { return -1; }

      if (a < b) { return -1 * sign; }
      if (a > b) { return 1 * sign; }
      return 0;
    };
  }

  /* config:
   *   tbody       the tbody whose rows are reordered
   *   rowSelector which of its rows are sortable records
   *   columns     [{ key, label, attr, type, asc, desc }] -- asc/desc are the
   *               words this column's two directions are described in, e.g.
   *               'A-Z' / 'Z-A' or 'Soonest first' / 'Latest first'
   *   initial     { key, direction } the order the server already sent
   *   companion   optional (row) -> element that must travel with the row, for a
   *               table whose records span more than one <tr>
   *   onChange    called with the resolved state after every sort
   */
  function create(config) {
    var tbody = config.tbody;
    var columns = config.columns;
    var state = {
      key: config.initial.key,
      direction: config.initial.direction || 'asc'
    };

    function columnFor(key) {
      for (var i = 0; i < columns.length; i++) {
        if (columns[i].key === key) { return columns[i]; }
      }
      return null;
    }

    function describe() {
      var column = columnFor(state.key);
      return {
        key: state.key,
        direction: state.direction,
        label: column ? column.label : '',
        // The direction in words rather than an arrow. The icon font here is a
        // fixed self-hosted subset and a ligature it does not carry renders as
        // the literal word (see medicine_inventory.html's note on `unarchive`),
        // so the one thing that must never be ambiguous is not left to a glyph.
        directionLabel: column ? (state.direction === 'desc' ? column.desc : column.asc) : ''
      };
    }

    function render() {
      var column = columnFor(state.key);
      if (!column) { return; }

      var rows = Array.prototype.slice.call(tbody.querySelectorAll(config.rowSelector));
      var ordered = stableSort(rows, comparator(column, state.direction));

      // Every companion is resolved HERE, while the table is still as the server
      // rendered it and before a single row has been moved.
      //
      // This is not a micro-optimisation, it is the whole correctness of the
      // pairing. A companion is found by looking at what sits next to its row,
      // and appendChild() *moves* an element rather than copying it -- so
      // resolving a companion after earlier rows had already been lifted out
      // would be asking "what follows this row?" of a table that is halfway
      // through being rebuilt. The answer comes back null, or worse, the
      // neighbouring record's panel, and every detail row ends up under the wrong
      // medicine.
      var pairs = ordered.map(function (row) {
        return { row: row, extra: config.companion ? config.companion(row) : null };
      });

      // Re-appending an element that is already in the DOM moves it; it is not a
      // copy, so every listener, checkbox tick and open detail panel survives the
      // reorder untouched. A fragment keeps it to one reflow rather than one per
      // row.
      var fragment = document.createDocumentFragment();
      pairs.forEach(function (pair) {
        fragment.appendChild(pair.row);
        if (pair.extra) { fragment.appendChild(pair.extra); }
      });
      tbody.appendChild(fragment);

      if (config.onChange) { config.onChange(describe()); }
    }

    return {
      /* Sort by a column. Asking for the column already sorted flips its
       * direction, which is what every table in the world does; asking for a
       * different one starts it in its own natural direction -- names open A-Z,
       * expiry dates open soonest-first -- rather than inheriting whichever way
       * the previous column happened to be pointing. */
      sortBy: function (key) {
        var column = columnFor(key);
        if (!column) { return; }
        if (state.key === key) {
          state.direction = state.direction === 'asc' ? 'desc' : 'asc';
        } else {
          state.key = key;
          state.direction = column.initialDirection || 'asc';
        }
        render();
      },
      state: describe,
      // Applies the initial state's labels without reordering anything: the
      // server already sent the rows in this order, so the first paint has
      // nothing to do but say what it is.
      announce: function () {
        if (config.onChange) { config.onChange(describe()); }
      }
    };
  }

  global.IDSTableSort = { create: create };
})(window);
