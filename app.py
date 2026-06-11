// ============================================
// GLOBAL CONFIGURATION
// ============================================
const DEBUG_MODE = false;
const GEMINI_URL_BASE = "https://generativelanguage.googleapis.com/v1beta/models/";

// === Bescos sheet columns (1-based) ===
const COL_LINK_DESC        = 1;   // Link / Description (manual info)
const COL_GUIDELINES       = 2;   // Guidelines
const COL_NAME             = 3;   // <Name>
const COL_SKU              = 4;   // SKU
const COL_MPN              = 5;   // ManufacturerPartNumber
const COL_HIERARCHY        = 6;   // MRK.Hierarchy
const COL_ERP_CATEGORY     = 7;   // ERP Product Category
const COL_PAR_COUNT        = 8;   // # Paragraphs
const COL_BANNER_FLAG      = 9;   // Banner
const COL_RAW_HTML         = 10;  // Description (Step 1 output – raw HTML)
const COL_TITLE            = 11;  // Title
const COL_INTRO            = 12;  // Εισαγωγή (Intro)

// Section pairs (BC* Title/Cont)
const COL_SEC1_HDR         = 13;  // BC1 Title
const COL_SEC1_BODY        = 14;  // BC1 Cont
const COL_SEC2_HDR         = 15;  // BC2 Title
const COL_SEC2_BODY        = 16;  // BC2 Cont
const COL_SEC3_HDR         = 17;  // BC3 Title
const COL_SEC3_BODY        = 18;  // BC3 Cont
const COL_SEC4_HDR         = 19;  // BC4 Title
const COL_SEC4_BODY        = 20;  // BC4 Cont
const COL_SEC5_HDR         = 21;  // BC5 Title
const COL_SEC5_BODY        = 22;  // BC5 Cont
const COL_SEC6_HDR         = 23;  // BC6 Title
const COL_SEC6_BODY        = 24;  // BC6 Cont
const COL_EXTRA_AFTER6    = 28;  // AB - Extra HTML μετά την Besco 6

const COL_TECHSPECS_HTML   = 25;  // TechSpecs (Step 4 output)
const COL_CATLINK          = 26;  // CatLink
const COL_FINAL_HTML       = 27;  // Output (Step 5 final)
const COL_CATEGORY         = 29;  // Category (tech/home/enter)
const COL_SEARCHED_FLAG    = 30;  // Searched online             
const COL_SEARCH_QUERY     = 31;  // Search Query                
const COL_SEARCH_LINK1     = 32;  // Searched Link 1             
const COL_SEARCH_LINK2     = 33;  // Searched Link 2            
const COL_SEARCH_LINK3     = 34;  // Searched Link 3             

let g_RunOnlyWhereAAEmpty = true;
let CatLinksDict = null;

// ============================================
// HELPERS
// ============================================
function getAPIKey() {
  // Always use the central hardcoded key
  return getGeminiApiKey();
}

function shouldRunRow_OutputEmpty(sheet, rowNum) {
  const val = sheet.getRange(rowNum, COL_FINAL_HTML).getValue();
  return !val || String(val).trim() === '';
}

function cleanTextInput(txt) {
  if (!txt) return '';
  // collapse all whitespace (tabs, NBSP, multiple spaces, newlines) to single space
  return String(txt)
    .replace(/[\uFEFF\u200B\u00A0]/g, ' ')
    .replace(/\s+/g, ' ')
    .replace(/;+/g, ',')   // your semicolon → comma rule
    .trim();
}

function cleanLower(s) {
  return cleanTextInput(s).toLowerCase();
}


let g_TechSpecsRowMap = null; // cache for current run

function buildTechSpecsRowMap() {
  if (g_TechSpecsRowMap) return g_TechSpecsRowMap;

  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const wsTech = ss.getSheetByName('TechSpecs');
  const lastRow = wsTech.getLastRow();
  const map = Object.create(null);

  if (lastRow >= 2) {
    // Column B holds the hierarchy list (comma-separated)
    const hierCol = wsTech.getRange(2, 2, lastRow - 1, 1).getValues();
    for (let i = 0; i < hierCol.length; i++) {
      const rowIndex = i + 2;
      const raw = cleanTextInput(hierCol[i][0]);
      if (!raw) continue;
      // split into tokens once; index each token → row
      raw.split(',').forEach(token => {
        const key = cleanLower(token);
        if (key && !map[key]) map[key] = rowIndex;
      });
    }
  }
  g_TechSpecsRowMap = map;
  return map;
}

function toPlainText(s) {
  return normalizeSpaces(stripAllTags(String(s || '')));
}

function showToast(message, title, seconds) {
  // Η Google επιτρέπει max 5s για toast. Βάζουμε default 5.
  SpreadsheetApp.getActiveSpreadsheet().toast(
    message,
    title || '',
    seconds != null ? Math.min(Math.max(seconds, 1), 5) : 5
  );
}

// === Start Bescos Orchestrator === //

function createBescosDescription() {
  // logUsage('createBescosDescription'); // Αν έχεις τη συνάρτηση logUsage
  
  // 1. Καθαρισμός παλιών triggers για να ξεκινήσουμε φρέσκοι
  deleteBescosContinuationTriggers();
  
  // 2. Αποθήκευση χρόνου έναρξης για το τελικό report
  PropertiesService.getScriptProperties().setProperty('BESCOS_TOTAL_START_TIME', new Date().getTime().toString());
  
  // 3. Ξεκινάμε από τη σειρά 2
  processBescosBatch(2);
}

function continueBescosDescription() {
  // Παίρνουμε τη σειρά από εκεί που σταματήσαμε
  const nextRow = parseInt(PropertiesService.getScriptProperties().getProperty('BESCOS_NEXT_ROW') || '2');
  processBescosBatch(nextRow);
}

function processBescosBatch(startRow) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sheet = ss.getSheetByName('Bescos');
  
  if (!sheet) {
    ss.toast('Error: Sheet "Bescos" not found.', 'Error', 10);
    deleteBescosContinuationTriggers();
    return;
  }
  
  const batchStartTime = new Date();
  const BATCH_SIZE = 10; // Λίγο μικρότερο batch γιατί τα Bescos είναι πιο "βαριά" κείμενα
  const TIME_LIMIT = 5.5 * 60 * 1000; // 5.5 λεπτά όριο
  
  ss.toast(`Processing batch starting from row ${startRow}...`, 'Processing', 5);
  
  try {
    const lastRow = sheet.getLastRow();
    
    // ΠΡΟΕΤΟΙΜΑΣΙΑ: Φορτώνουμε τα Dictionaries ΜΙΑ φορά ανά batch για ταχύτητα
    // Αυτό είναι το "μυστικό" από τις Bullets
    const catLinksDict = initializeCatLinksDict(); // Από το Step 3 σου
    const techRowMap = buildTechSpecsRowMap();    // Από το Step 4 σου
    const headersData = wsS.getRange(1, 1, 1, wsS.getLastColumn()).getValues();
	  //const specsData   = wsS.getDataRange().getValues();
	  const techData = ss.getSheetByName('TechSpecs').getDataRange().getValues();
	  const specsData = ss.getSheetByName('Specs').getDataRange().getValues();
	  const specsHeaders = specsData[0].map(h => cleanLower(h));
	
    let processedCount = 0;
    
    for (let row = startRow; row <= lastRow; row++) {
      
      // Α) ΕΛΕΓΧΟΣ ΧΡΟΝΟΥ
      const elapsed = new Date() - batchStartTime;
      if (elapsed > TIME_LIMIT) {
        createBescosContinuationTrigger(row);
        ss.toast(`Time limit reached at row ${r}. Automatically resuming soon...`, 'Auto-Continue', 5);
        return;
      }
      
      // Β) ΕΛΕΓΧΟΣ ΑΝ ΠΡΕΠΕΙ ΝΑ ΤΡΕΞΕΙ (Αν π.χ. λείπει το SKU ή είναι ήδη έτοιμο)
      const sku = sheet.getRange(row, COL_SKU).getValue();
      if (!sku) continue;
      
      // Αν η στήλη AA (Final HTML) είναι ήδη γεμάτη, προσπέρασε
      if (sheet.getRange(row, COL_FINAL_HTML).getValue() !== "") continue;
      
      ss.toast(`Processing product ${r-1} of ${lastRow-1}...`, 'Progress', 3);

      // Γ) ΕΚΤΕΛΕΣΗ ΤΩΝ 5 STEPS (Προσαρμοσμένα για τη σειρά 'row')
      
      // Step 3: Κατηγοριοποίηση (χρησιμοποιώντας το dict στη μνήμη)
	  step3_OutputCatLinks(row, catLinksDict);
      
      // Step 1: Gemini API
	  step1_GenHTMLGemini(row, headersData, specsData);
      
      // Step 2: Parsing (Title, Intro, BC1-6)
      step2_ParseSections(row); 
      
      // Step 4: Tech Specs HTML (χρησιμοποιώντας το map στη μνήμη)
      const specsHtml = generateSpecsHTML_UsingMap(row, techRowMap);
      sheet.getRange(row, COL_TECHSPECS_HTML).setValue(specsHtml);
      step4_ProcessSpecsRow(row, techRowMap, techData, specsHeaders, specsData);
	  
      // Step 5: Τελικό Merge & Styling
      step5_GenerateProductHTML(row); 

      // Ενημέρωση του Sheet
      SpreadsheetApp.flush();
      
      processedCount++;
      
      // Δ) ΕΛΕΓΧΟΣ BATCH SIZE
      if (processedCount >= BATCH_SIZE) {
        if (row + 1 <= lastRow) {
          createBescosContinuationTrigger(row + 1);
          ss.toast(`Batch completed. Continuing automatically in 1 minute...`, 'Progress', 5);
          return;
        }
        break;
      }
    }
    
    // ΤΕΛΟΣ ΔΙΑΔΙΚΑΣΙΑΣ
    const totalStartTime = parseInt(PropertiesService.getScriptProperties().getProperty('BESCOS_TOTAL_START_TIME') || new Date().getTime());
    const totalDuration = Math.round((new Date().getTime() - totalStartTime) / 1000);
    
    deleteBescosContinuationTriggers();
    ss.toast(`✅ Completed! Total time: ${totalDuration}s | Products: ${processedCount}`, 'Success', -1);
    
  } catch (error) {
    deleteBescosContinuationTriggers();
    ss.toast('Error: ' + error.toString(), 'Error', 10);
    Logger.log('ERROR: ' + error.toString());
  }
}

// === Trigger Helpers (Απαραίτητα για τη συνέχεια) ===

function createBescosContinuationTrigger(nextRow) {
  deleteBescosContinuationTriggers();
  PropertiesService.getScriptProperties().setProperty('BESCOS_NEXT_ROW', nextRow.toString());
  ScriptApp.newTrigger('continueBescosDescription')
    .timeBased()
    .after(60 * 1000) 
    .create();
}

function deleteBescosContinuationTriggers() {
  const triggers = ScriptApp.getProjectTriggers();
  triggers.forEach(t => {
    if (t.getHandlerFunction() === 'continueBescosDescription' || t.getHandlerFunction() === 'processBescosBatch') {
      ScriptApp.deleteTrigger(t);
    }
  });
}

// ============================================
// STEP 1: GENERATE HTML WITH GEMINI (ROW VERSION)
// ============================================
function step1_GenHTMLGemini(rowNum, headersData, specsData) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const wsB = ss.getSheetByName('Bescos');
  
  const apiKey = getAPIKey();
  if (!apiKey) return;

  // Διαβάζουμε τα δεδομένα ΜΟΝΟ της συγκεκριμένης σειράς από το Bescos
  const lastColB = wsB.getLastColumn();
  const rowData = wsB.getRange(rowNum, 1, 1, lastColB).getValues()[0];

  const productName   = rowData[COL_NAME - 1];
  const mpn           = rowData[COL_MPN - 1];
  const numParagraphs = rowData[COL_PAR_COUNT - 1];
  const manualInfo    = cleanTextInput(rowData[COL_LINK_DESC - 1]);
  const promptType    = cleanLower(rowData[COL_CATEGORY - 1]);
  const guidelines    = cleanTextInput(rowData[COL_GUIDELINES - 1]);

  if (!productName) return;

  const useOnlineSearch = !manualInfo;
  // Προσοχή: στο specsData το index είναι rowNum-1 λόγω 0-based array
  const techSpecs   = buildTechSpecs(rowNum - 1, headersData, specsData);
  const searchQuery = [productName, mpn].filter(Boolean).join(' ');

  let styleInstructions, contentTemplate;
  switch (promptType) {
    case 'tech':
      styleInstructions = buildStyle_Tech();
      contentTemplate = useOnlineSearch
        ? buildContent_Tech_Online(searchQuery, numParagraphs)
        : buildContent_Tech_Offline(manualInfo, numParagraphs, techSpecs);
      break;
    case 'home':
      styleInstructions = buildStyle_Home();
      contentTemplate = useOnlineSearch
        ? buildContent_Home_Online(searchQuery, numParagraphs)
        : buildContent_Home_Offline(manualInfo, numParagraphs, techSpecs);
      break;
    case 'enter':
      styleInstructions = buildStyle_Enter();
      contentTemplate = useOnlineSearch
        ? buildContent_Enter_Online(searchQuery, numParagraphs)
        : buildContent_Enter_Offline(manualInfo, numParagraphs, techSpecs);
      break;
    default:
      wsB.getRange(rowNum, COL_RAW_HTML).setValue('Σφάλμα: Άκυρος τύπος (στήλη AC).');
      return;
  }

  const guidelinesBlock = guidelines ? `ΚΡΙΣΙΜΕΣ ΟΔΗΓΙΕΣ ΠΟΥ ΠΡΕΠΕΙ ΝΑ ΑΚΟΛΟΥΘΗΣΕΙΣ:\n${guidelines}\n\n` : '';
  if (!useOnlineSearch) {
    const sourceBlock = `4) Υλικό Αναφοράς:\n${manualInfo || techSpecs}`;
    contentTemplate = contentTemplate.replace('###SOURCE_BLOCK###', sourceBlock);
  } else {
    contentTemplate = contentTemplate.replace('###SOURCE_BLOCK###', '');
  }

  const promptTemplate = guidelinesBlock + styleInstructions + '\n\n' + contentTemplate;

  const n = parseInt(numParagraphs) || 0;
  let maxToks = 1800 + 1200 * n;
  if (maxToks > 32000) maxToks = 32000;

  const requestBody = {
    model: getGeminiModel(),
    generationConfig: { maxOutputTokens: maxToks },
    contents: [{ parts: [{ text: promptTemplate }] }]
  };
  if (useOnlineSearch) requestBody.tools = [{ google_search: {} }];

  // Χρήση της δικής σου callGeminiWithRetry
  const result = callGeminiWithRetry(apiKey, requestBody);

  // Απευθείας εγγραφή στη σειρά (Row-by-Row)
  if (result.success) {
    wsB.getRange(rowNum, COL_RAW_HTML).setValue(result.text);
    if (result.searchUsed) {
      wsB.getRange(rowNum, COL_SEARCHED_FLAG).setValue('!! Grounding used');
      wsB.getRange(rowNum, COL_SEARCH_QUERY).setValue(result.searchUsed || '');
    } else {
      wsB.getRange(rowNum, COL_SEARCHED_FLAG).setValue('');
      wsB.getRange(rowNum, COL_SEARCH_QUERY).setValue('');
    }
    wsB.getRange(rowNum, COL_SEARCH_LINK1).setValue(result.links[0] || '');
    wsB.getRange(rowNum, COL_SEARCH_LINK2).setValue(result.links[1] || '');
    wsB.getRange(rowNum, COL_SEARCH_LINK3).setValue(result.links[2] || '');
  } else {
    wsB.getRange(rowNum, COL_SEARCHED_FLAG).setValue('TIMEOUT/HTTP');
    wsB.getRange(rowNum, COL_SEARCH_QUERY).setValue(result.error);
  }
}

// PERFORMANCE FIX: Helper to batch write updates
function flushUpdates(sheet, updates, numCols) {
  updates.forEach(update => {
    sheet.getRange(update.row + 1, 1, 1, numCols).setValues([update.data]);
  });
  SpreadsheetApp.flush();
}

function callGeminiWithRetry(apiKey, requestBody) {
  const url = `${GEMINI_URL_BASE}${getGeminiModel()}:generateContent?key=${apiKey}`;
  for (let attempt = 1; attempt <= 4; attempt++) {
    try {
      const options = {
        method: 'post',
        contentType: 'application/json',
        payload: JSON.stringify(requestBody),
        muteHttpExceptions: true
      };
      const response = UrlFetchApp.fetch(url, options);
      const statusCode = response.getResponseCode();

      if (statusCode === 200) return parseGeminiResponse(response.getContentText());

      if ([408, 429, 500, 502, 503, 504].includes(statusCode)) {
        Utilities.sleep(Math.pow(2, attempt - 1) * 1000);
        continue;
      }
      return { success: false, error: `HTTP ${statusCode}: ${response.getContentText()}` };
    } catch (e) {
      if (attempt === 4) return { success: false, error: e.toString() };
      Utilities.sleep(Math.pow(2, attempt - 1) * 1000);
    }
  }
  return { success: false, error: 'Max retry attempts exceeded' };
}

function parseGeminiResponse(responseText) {
  try {
    const json = JSON.parse(responseText);
    let generatedText = '', searchUsed = '';
    const links = ['', '', ''];

    if (json.candidates && json.candidates[0]) {
      const cand = json.candidates[0];
      if (cand.content?.parts?.[0]) generatedText = cand.content.parts[0].text || '';
      if (cand.groundingMetadata) {
        const gm = cand.groundingMetadata;
        if (gm.webSearchQueries?.[0]) searchUsed = gm.webSearchQueries[0];
        if (gm.groundingChunks) {
          for (let i = 0; i < Math.min(3, gm.groundingChunks.length); i++) {
            const uri = gm.groundingChunks[i]?.web?.uri;
            if (uri) links[i] = uri;
          }
        }
      }
    }
    return { success: true, text: generatedText, searchUsed, links };
  } catch {
    const match = responseText.match(/"text"\s*:\s*"([^"]*)"/);
    const text = match ? match[1].replace(/\\n/g, '\n') : '';
    return { success: true, text, searchUsed: '', links: ['', '', ''] };
  }
}

function buildTechSpecs(productRow, headers, specs) {
  if (!headers || !specs || productRow >= specs.length) return 'Τεχνικά Χαρακτηριστικά\n(δεν βρέθηκαν διαθέσιμα στοιχεία)';
  const buf = [];
  for (let c = 0; c < headers[0].length; c++) {
    const attributeName = cleanTextInput(headers[0][c]);
    const attributeValue = cleanTextInput(specs[productRow][c]);
    if (attributeValue) buf.push(`${attributeName}: ${attributeValue}`);
  }
  return buf.length ? ('Τεχνικά Χαρακτηριστικά\n' + buf.join('\n'))
                    : 'Τεχνικά Χαρακτηριστικά\n(δεν βρέθηκαν διαθέσιμα στοιχεία)';
}



// ============================================
// STEP 2: PARSE SECTIONS FROM HTML (SINGLE ROW VERSION)
// ============================================
function step2_ParseSections(rowNum) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const ws = ss.getSheetByName('Bescos');
  
  // 1. CONFIGURATION (Σταθερές από το Config σου)
  // Χρησιμοποιούμε τις COL_... που όρισες στην κορυφή του αρχείου
  
  // Διαβάζουμε ΜΟΝΟ τη συγκεκριμένη σειρά
  const lastCol = ws.getLastColumn();
  const rowRange = ws.getRange(rowNum, 1, 1, lastCol);
  const rowData = rowRange.getValues()[0];

  // Παίρνουμε το HTML από τη στήλη J (COL_RAW_HTML)
  let rawHtml = String(rowData[COL_RAW_HTML - 1] || '');

  // Αν είναι άδειο, σταμάτα
  if (!rawHtml.trim()) {
    return;
  }

  // 3. NORMALIZE (Οι δικοί σου Helpers παραμένουν ίδιοι)
  rawHtml = normalizeHeaders(rawHtml);
  rawHtml = normalizeHeaders(rawHtml); // Twice as per VBA
  rawHtml = promoteFirstH2ToH1(rawHtml);

  // 4. PARSE
  const lines = htmlToLines(rawHtml);
  const sections = parseSections_VBA_Style(lines);

  // 5. ΠΡΟΕΤΟΙΜΑΣΙΑ ARRAY ΓΙΑ OUTPUT (K έως X και AB)
  // Φτιάχνουμε έναν πίνακα με κενά για να καθαρίσουμε τις παλιές τιμές
  // Από COL_TITLE (11) έως COL_SEC6_BODY (24) είναι 14 στήλες
  let outputRow = new Array(14).fill(''); 
  let extraText = '';

  // 6. OUTPUT LOGIC (Η δική σου λογική)
  if (sections.length > 0) {
    let outIdx = 0; // Δείκτης για το outputRow (0 = Col K, 1 = Col L...)
    let startIdx = 0;

    // Special Case: Αν το 1ο section δεν έχει header -> Intro
    if (!sections[0].header) {
      outputRow[0] = convertMarkdownBold(sections[0].content); // Col K
      outIdx = 2; // Πήδα στο M (BC1 Title)
      startIdx = 1;
    }

    let extras = [];
    for (let i = startIdx; i < sections.length; i++) {
      const hdr = sections[i].header;
      const txt = convertMarkdownBold(sections[i].content);

      if (outIdx + 1 < outputRow.length) {
        outputRow[outIdx]     = hdr; // Header
        outputRow[outIdx + 1] = txt; // Content
        outIdx += 2;
      } else {
        // Overflow για τη στήλη AB
        if (hdr) extras.push(`Τίτλος: ${stripAllTags(hdr)}`);
        extras.push(`Κείμενο: ${stripAllTags(txt)}`);
      }
    }
    extraText = extras.join('\n');
  }

  // 7. ΕΓΓΡΑΦΗ ΠΙΣΩ ΣΤΟ SHEET
  // Γράφουμε τις στήλες K έως X (14 στήλες)
  ws.getRange(rowNum, COL_TITLE, 1, 14).setValues([outputRow]);
  
  // Γράφουμε το Extra στο AB (28)
  if (extraText) {
    ws.getRange(rowNum, COL_EXTRA_AFTER6).setValue(extraText);
  }
}

// =======================
// CORE PARSING LOGIC (FIXED)
// =======================

function parseSections_VBA_Style(lines) {
  const sections = [];
  let curHeader = '';
  let curBody = '';
  let introParagraphs = [];

  for (let i = 0; i < lines.length; i++) {
    if (lines[i] == null) continue;
    let lineText = normalizeSpaces(String(lines[i]).trim());

    if (!lineText) continue;

    // Skip scaffolding divs
    const low = lineText.toLowerCase();
    if (low.startsWith('<div') || low.startsWith('</div')) continue;

    const hasFoundHeader = sections.length > 0 || curHeader !== '';

    // --- PRIORITY 1: HTML H1-H3 HEADERS (Must check FIRST) ---
    if (isHtmlHeader(lineText)) {
      if (introParagraphs.length > 0) {
        sections.push({ header: '', content: introParagraphs.join(' ') });
        introParagraphs = [];
      }
      commitSection(sections, curHeader, curBody);
      curHeader = extractHeaderTag(lineText);
      curBody = '';
      continue;
    }

    // --- PRIORITY 2: Markdown Headers (### or **Title**:) ---
    if (lineText.startsWith('###')) {
      if (introParagraphs.length > 0) {
        sections.push({ header: '', content: introParagraphs.join(' ') });
        introParagraphs = [];
      }
      commitSection(sections, curHeader, curBody);
      curHeader = extractHeaderTag(lineText);
      curBody = '';
      continue;
    }

    // --- PRIORITY 3: Markdown Bold Headers **Title**: or **Title** (standalone) ---
    if (lineText.startsWith('**')) {
      const boldEnd = lineText.indexOf('**', 2);
      if (boldEnd > 0) {
        const after = lineText.substring(boldEnd + 2).trim();
        
        // **Title**: Content or **Title**. Content
        if (after.length > 0 && '.:?!'.includes(after.charAt(0))) {
          if (introParagraphs.length > 0) {
            sections.push({ header: '', content: introParagraphs.join(' ') });
            introParagraphs = [];
          }
          commitSection(sections, curHeader, curBody);
          curHeader = lineText.substring(2, boldEnd);
          curBody = after.substring(1).trim(); // Skip punctuation
          continue;
        }
        // **Title** at end of line - this is a header
        else if (lineText.endsWith('**') && after.length === 0) {
          if (introParagraphs.length > 0) {
            sections.push({ header: '', content: introParagraphs.join(' ') });
            introParagraphs = [];
          }
          commitSection(sections, curHeader, curBody);
          curHeader = lineText.substring(2, boldEnd);
          curBody = '';
          continue;
        }
      }
    }

    // --- PRIORITY 4: <strong>Title</strong> with Tagline ---
    if (startsWithStrong(lineText)) {
      const extracted = extractStrongAndTail(lineText);
      if (extracted && extracted.tail !== undefined && looksLikeHeaderTagline(extracted.tail)) {
        if (introParagraphs.length > 0) {
          sections.push({ header: '', content: introParagraphs.join(' ') });
          introParagraphs = [];
        }
        commitSection(sections, curHeader, curBody);
        curHeader = extracted.strongText;
        curBody = extracted.tail;
        continue;
      }
    }

    // --- PRIORITY 5: Pure <strong>...</strong> (Standalone header) ---
    if (isPureStrong(lineText)) {
      if (introParagraphs.length > 0) {
        sections.push({ header: '', content: introParagraphs.join(' ') });
        introParagraphs = [];
      }
      commitSection(sections, curHeader, curBody);
      curHeader = stripStrong(lineText);
      curBody = '';
      continue;
    }

    // --- PRIORITY 6: Headerish Plain Text (Last resort) ---
    // IMPORTANT: Only treat as header if we DON'T already have a pending header
    if (!hasFoundHeader && isHeaderish(lineText)) {
      if (introParagraphs.length > 0) {
        sections.push({ header: '', content: introParagraphs.join(' ') });
        introParagraphs = [];
      }
      commitSection(sections, curHeader, curBody);
      curHeader = lineText;
      curBody = '';
      continue;
    }

    // --- DEFAULT: Body Content ---
    if (!hasFoundHeader) {
      // Still in intro section
      introParagraphs.push(lineText);
    } else {
      // Regular body content - append to current section
      curBody = curBody ? (curBody + ' ' + lineText) : lineText;
    }
  }

  // Final commits
  if (introParagraphs.length > 0) {
    sections.push({ header: '', content: introParagraphs.join(' ') });
  }
  commitSection(sections, curHeader, curBody);
  
  return sections;
}

function commitSection(sections, hdr, body) {
  const h = (hdr || '').trim();
  const b = (body || '').trim();
  if (h || b) {
    sections.push({ header: h, content: b });
  }
}

// =======================
// HELPERS
// =======================

function isHtmlHeader(line) {
  return /^<h[1-3]\b/i.test(line.trim());
}

function normalizeHeaders(html) {
  if (!html) return '';
  
  // Remove nested <p> tags
  html = html.replace(/<p>\s*<p>/gi, '<p>');
  html = html.replace(/<\/p>\s*<\/p>/gi, '</p>');
  
  // Remove p around h1-h3
  html = html.replace(/<p>\s*(<h[1-3]\b[^>]*>.*?<\/h[1-3]>)\s*<\/p>/gi, '$1');
  html = html.replace(/<p>\s*(<h[1-3]\b[^>]*>)/gi, '$1');
  html = html.replace(/<\/h([1-3])>\s*<\/p>/gi, '</h$1>');
  
  // Remove doctype/html/body
  html = html.replace(/<!DOCTYPE[^>]*>/gi, '');
  html = html.replace(/<\/?(?:html|head|body)[^>]*>/gi, '');
  
  return html;
}

function promoteFirstH2ToH1(html) {
  if (!html) return '';
  if (!/<h1\b[^>]*>/i.test(html)) {
    html = html.replace(/<h2\b/i, '<h1');
    html = html.replace(/<\/h2>/i, '</h1>');
  }
  return html;
}

function htmlToLines(html) {
  if (!html) return [];
  html = String(html);
  
  // Cut before first h1
  const p = html.toLowerCase().indexOf('<h1>');
  if (p > 0) html = html.substring(p);
  
  // Normalize spaces
  html = html.replace(/\xA0/g, ' ').replace(/&nbsp;/g, ' ');
  html = html.replace(/```html/g, '').replace(/```/g, '');
  
  // Line breaks
  html = html.replace(/\r\n/g, '\n').replace(/\r/g, '\n');
  html = html.replace(/<p>/gi, '\n<p>');
  html = html.replace(/<\/p>/gi, '</p>\n');
  html = html.replace(/<br\s*\/?>/gi, '\n');
  
  // Split and clean
  const lines = html.split('\n');
  const cleaned = [];
  
  for (let line of lines) {
    line = line.trim();
    if (!line) continue;
    
    // Remove <p> tags but keep content
    line = line.replace(/^<p>/i, '').replace(/<\/p>$/i, '');
    line = line.trim();
    
    if (line) cleaned.push(line);
  }
  
  return cleaned;
}

function normalizeSpaces(s) {
  if (!s) return '';
  return s.replace(/\s+/g, ' ').trim();
}

function startsWithStrong(s) {
  return s.toLowerCase().startsWith('<strong>');
}

function isPureStrong(s) {
  s = s.trim();
  if (!s.toLowerCase().startsWith('<strong>')) return false;
  if (!s.toLowerCase().endsWith('</strong>')) return false;
  const inner = stripStrong(s);
  return inner.length > 0 && !inner.includes('<strong>');
}

function stripStrong(s) {
  return s.replace(/<\/?strong>/gi, '').trim();
}

function extractStrongAndTail(s) {
  if (!s) return null;
  const pOpen = s.toLowerCase().indexOf('<strong>');
  if (pOpen !== 0) return null;
  
  const pClose = s.toLowerCase().indexOf('</strong>', pOpen + 8);
  if (pClose === -1) return null;
  
  const strongText = s.substring(pOpen + 8, pClose);
  
  // Safety: Always ensure tail is a string, never undefined
  let tail = '';
  try {
    const rawTail = s.substring(pClose + 9);
    if (rawTail !== undefined && rawTail !== null) {
      tail = String(rawTail).trim();
    }
  } catch (e) {
    tail = '';
  }
  
  return { strongText: strongText, tail: tail };
}

function isHeaderish(s) {
  s = s.trim();
  // Must be reasonable length
  if (!s || s.length < 8 || s.length > 120) return false;
  // Must not contain HTML tags or markdown
  if (s.includes('<') || s.includes('>')) return false;
  if (s.startsWith('**') || s.endsWith('**')) return false;
  if (s.startsWith('-') || s.startsWith('•')) return false;
  
  // Must end with header-like punctuation
  const lastCh = s.slice(-1);
  return '.:…'.includes(lastCh);
}

function looksLikeHeaderTagline(afterClose) {
  // Safety: Handle undefined/null/empty
  if (afterClose === undefined || afterClose === null || afterClose === '') return false;
  
  // Convert to string safely
  try {
    afterClose = String(afterClose).trim();
  } catch (e) {
    return false;
  }
  
  if (!afterClose) return false;
  
  afterClose = normalizeSpaces(afterClose);
  const words = afterClose.split(' ').length;
  if (words <= 12) return true;
  return afterClose.length <= 140; 
}

function extractHeaderTag(lineText) {
  const t = lineText.trim();
  
  // Handle ### markdown headers
  if (t.startsWith('#')) {
    return t.replace(/^#{1,6}\s*/, '').trim();
  }
  
  // Handle HTML headers - strip all tags
  return stripAllTags(lineText);
}

function stripAllTags(html) {
  if (html == null) return '';
  return String(html).replace(/<[^>]*>/g, '').trim();
}

function convertMarkdownBold(s) {
  if (!s) return '';
  s = String(s);
  while (true) {
    const p1 = s.indexOf('**');
    if (p1 === -1) break;
    const p2 = s.indexOf('**', p1 + 2);
    if (p2 === -1) break;
    s = s.substring(0, p1) + '<strong>' + s.substring(p1 + 2, p2) + '</strong>' + s.substring(p2 + 2);
  }
  return s;
}

// ============================================
// STEP 3: OUTPUT CATEGORY LINKS
// ============================================

let g_CatLinksDict = null; // In-memory cache

/**
 * Build CatLinksDict from CatLinks sheet
 */
function buildCatLinksDict() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const wsCat = ss.getSheetByName('CatLinks');
  const lastRow = wsCat.getLastRow();

  const dict = Object.create(null);
  
  if (lastRow >= 2) {
    const data = wsCat.getRange(2, 1, lastRow - 1, 14).getValues();
    
    for (let r = 0; r < data.length; r++) {
      const tokensCSV = cleanTextInput(data[r][4]);     // Column E (index 4) - ERP/MRK
      if (!tokensCSV) continue;
      
      const categoryName = cleanTextInput(data[r][2]);  // Column C (index 2) - Category Name
      const link = cleanTextInput(data[r][13]);         // Column N (index 13) - Link

      // Split comma-separated tokens and add each as a key
      tokensCSV.split(',').forEach(tok => {
        const key = cleanLower(tok);
        if (key && !dict[key]) {
          dict[key] = { link, categoryName };
        }
      });
    }
  }
  
  g_CatLinksDict = dict;
  Logger.log('CatLinksDict built in memory with ' + Object.keys(dict).length + ' entries');
  return dict;
}

/**
 * Get CatLinksDict (build if not already in memory)
 */
function getCatLinksDictForStep3() {
  if (!g_CatLinksDict) {
    Logger.log('Building CatLinksDict from CatLinks sheet...');
    buildCatLinksDict();
  }
  
  return g_CatLinksDict || Object.create(null);
}

/**
 * Get category link and name for a product row
 * Strategy:
 * 1. Try Column G (ERP product category)
 * 2. Try Column F (Hierarchy/MRK)
 * 3. If no match, return empty
 */
function getCatLinkAndNameForRowStep3(productRow) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const wsBescos = ss.getSheetByName('Bescos');
  const CatLinksDict = getCatLinksDictForStep3();

  if (!CatLinksDict || Object.keys(CatLinksDict).length === 0) {
    Logger.log('CatLinksDict is empty');
    return { link: '', categoryName: '' };
  }

  // Strategy 1: Try Column G (ERP product category) first
  let raw = cleanTextInput(wsBescos.getRange(productRow, 7).getValue()); // Column G
  
  if (raw) {
    const keyG = cleanLower(raw);
    const hitG = CatLinksDict[keyG];
    if (hitG) {
      Logger.log('Row ' + productRow + ': Found match in Column G (ERP): "' + raw + '" → ' + hitG.categoryName);
      return hitG;
    }
  }

  // Strategy 2: Try Column F (Hierarchy/MRK) if G didn't match
  raw = cleanTextInput(wsBescos.getRange(productRow, 6).getValue()); // Column F
  
  if (raw) {
    const keyF = cleanLower(raw);
    const hitF = CatLinksDict[keyF];
    if (hitF) {
      Logger.log('Row ' + productRow + ': Found match in Column F (Hierarchy): "' + raw + '" → ' + hitF.categoryName);
      return hitF;
    }
  }

  Logger.log('Row ' + productRow + ': No match found (checked G and F)');
  return { link: '', categoryName: '' };
}

/**
 * Main function: Output category links and names to Bescos sheet
 * Link → Column Z (26), Category Name → Column AC (29)
 */
function step3_OutputCatLinks(rowNum, CatLinksDict) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const wsBescos = ss.getSheetByName('Bescos');

  if (!CatLinksDict || Object.keys(CatLinksDict).length === 0) {
    return { link: '', categoryName: '' };
  }

  // Παίρνουμε τα δεδομένα των στηλών F (6) και G (7) με μία κλήση
  const rowData = wsBescos.getRange(rowNum, 6, 1, 2).getValues()[0];
  const valF = cleanTextInput(rowData[0]); // Column F (Hierarchy)
  const valG = cleanTextInput(rowData[1]); // Column G (ERP Category)

  let result = { link: '', categoryName: '' };

  // Strategy 1: Try Column G (ERP product category) first
  if (valG) {
    const hitG = CatLinksDict[cleanLower(valG)];
    if (hitG) result = hitG;
  }

  // Strategy 2: Try Column F (Hierarchy/MRK) if G didn't match
  if (!result.link && valF) {
    const hitF = CatLinksDict[cleanLower(valF)];
    if (hitF) result = hitF;
  }

  // Εγγραφή στο Sheet (Στήλη Z=26 και AC=29)
  // Χρησιμοποιούμε τις σταθερές σου COL_CATLINK και COL_CATEGORY
  wsBescos.getRange(rowNum, COL_CATLINK).setValue(result.link);
  wsBescos.getRange(rowNum, COL_CATEGORY).setValue(result.categoryName);

  return result;
}

/**
 * Refresh the CatLinksDict cache - call this after updating CatLinks sheet
 */
function refreshCatLinksDict() {
  Logger.log('Refreshing CatLinksDict...');
  g_CatLinksDict = null; // Clear existing cache
  buildCatLinksDict();
  Logger.log('CatLinksDict refreshed successfully');
  showToast('Category links cache refreshed', 'Done', 2);
}


// ============================================
// STEP 4: GENERATE SPECS HTML
// ============================================

function generateSpecsHTML_Optimized(productRow, techRowMap, techData, specsHeaders, specsData) {
  try {
    // 1. Χρήση της δικής σου λογικής για Hierarchy (F & G)
    const hierarchy = getProductHierarchyFromData(productRow); 
    if (!hierarchy) return '';

    // 2. Χρήση της δικής σου findTechSpecsRowFromMap
    const techRow = findTechSpecsRowFromMap(hierarchy, techRowMap);
    if (!techRow || techRow < 2) return '';

    // 3. Λήψη δεδομένων από το techData (array) αντί για το Sheet
    const rowValues = techData[techRow - 1];

    // Αντιστοίχιση στηλών (img, title, search)
    const features = [
      { img: rowValues[2],  title: rowValues[3],  search: rowValues[4] },
      { img: rowValues[5],  title: rowValues[6],  search: rowValues[7] },
      { img: rowValues[8],  title: rowValues[9],  search: rowValues[10] },
      { img: rowValues[11], title: rowValues[12], search: rowValues[13] }
    ];

    let html = '<div class="rich-multemedia">\n  <section class="features">\n';
    html += '    <div class="column"><h3><strong>Τεχνικά Χαρακτηριστικά</strong></h3></div>\n';
    html += '    <div class="column">\n';

    // 4. Χρήση του specsData (array) για να βρούμε τις τιμές
    features.forEach(f => {
      const strongVal = getAttributeValueFromSpecsArray(f.search, productRow, specsHeaders, specsData);
      html += buildFeatureHTML(cleanTextInput(f.img), cleanTextInput(f.title), strongVal);
    });

    html += '    </div>\n  </section>\n</div>';
    return html;
  } catch (e) { 
    Logger.log("Error in Step 4 for row " + productRow + ": " + e.message);
    return ''; 
  }
}

function step4_ProcessSpecsRow(rowNum, techRowMap, techData, specsHeaders, specsData) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const wsBescos = ss.getSheetByName('Bescos');
  
  // Καλούμε τη "μηχανή" παραγωγής HTML για τη συγκεκριμένη σειρά
  const specsHtml = generateSpecsHTML_Optimized(rowNum, techRowMap, techData, specsHeaders, specsData);
  
  // Γράφουμε το αποτέλεσμα στη στήλη COL_TECHSPECS_HTML (31)
  wsBescos.getRange(rowNum, COL_TECHSPECS_HTML).setValue(specsHtml);
}

function cleanSpecsHeaders() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const wsSpecs = ss.getSheetByName('Specs');
  const lastCol = wsSpecs.getLastColumn();
  const headers = wsSpecs.getRange(1, 1, 1, lastCol).getValues()[0];
  
  for (let c = 0; c < headers.length; c++) {
    headers[c] = cleanTextInput(headers[c]);
  }
  
  wsSpecs.getRange(1, 1, 1, lastCol).setValues([headers]);
}


function getProductHierarchyFromData(r) {
  const wsFull = SpreadsheetApp.getActiveSpreadsheet().getSheetByName('Bescos');
  // Διαβάζουμε F και G μαζί για ταχύτητα
  const data = wsFull.getRange(r, 6, 1, 2).getValues()[0];
  const erpCategory = cleanTextInput(data[1]); // Column G
  if (erpCategory) return erpCategory;
  return cleanTextInput(data[0]); // Column F fallback
}

function findTechSpecsRowFromMap(hierarchy, rowMap) {
  if (!hierarchy) return 0;
  const raw = cleanTextInput(hierarchy);
  const parts = raw.split(',');
  for (let i = 0; i < parts.length; i++) {
    const key = cleanLower(parts[i]);
    if (key && rowMap[key]) return rowMap[key];
  }
  return rowMap[cleanLower(raw)] || 0;
}


let g_SpecsHeaderMap = null;
let g_SpecsHeadersRow = null;

function buildHeaderIndexMap(headersRow) {
  const map = Object.create(null);
  headersRow.forEach((h, i) => {
    const key = cleanLower(h);
    if (key) map[key] = i;   // store zero-based col index
  });
  return map;
}

function ensureSpecsHeaderMap() {
  if (g_SpecsHeaderMap) return g_SpecsHeaderMap;
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const wsSpecs = ss.getSheetByName('Specs');
  const lastCol = wsSpecs.getLastColumn();
  const headers = wsSpecs.getRange(1, 1, 1, lastCol).getValues()[0];
  g_SpecsHeadersRow = headers;
  g_SpecsHeaderMap = buildHeaderIndexMap(headers);
  return g_SpecsHeaderMap;
}

/**
 * Fast spec value lookup without re-lowering in a loop.
 * Reads a single cell by (productRow, resolved column).
 */
function getAttributeValueFromSpecsArray(attributeID, productRow, specsHeaders, specsData) {
  if (!attributeID) return '-';
  const key = cleanLower(attributeID);
  const colIdx = specsHeaders.indexOf(key);
  if (colIdx === -1) return '-';
  
  // productRow-1 γιατί το array specsData ξεκινάει από τη σειρά 1
  const val = specsData[productRow - 1] ? specsData[productRow - 1][colIdx] : '-';
  return cleanTextInput(val) || '-';
}


function buildFeatureHTML(img, alt, strongVal) {
  if (!img || img === '-') return ''; 
  let block = '      <div class="feature">\n';
  block += '        <figure class="embed-responsive embed-responsive-21by9">\n';
  block += `          <img class="embed-responsive-item" src="${img}" alt="${alt}" loading="lazy">\n`;
  block += '        </figure>\n';
  block += `        <div class="body-text"><p>${alt} <strong class="d-block">${strongVal}</strong></p></div>\n`;
  block += '      </div>\n';
  return block;
}

// ============================================
// STEP 5: GENERATE PRODUCT HTML (SINGLE ROW)
// ============================================

function step5_GenerateProductHTML(rowNum) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const wsBescos = ss.getSheetByName('Bescos');
  const wsSpecs = ss.getSheetByName('Specs');
  
  // 1. Λήψη δεδομένων ΜΟΝΟ για τη συγκεκριμένη σειρά
  // Παίρνουμε όλη τη σειρά από το Bescos (Α έως AH)
  const rowData = wsBescos.getRange(rowNum, 1, 1, wsBescos.getLastColumn()).getValues()[0];
  
  // Παίρνουμε το Trailer (συνήθως τελευταία ή προτελευταία στήλη στο Specs)
  const lastColSpecs = wsSpecs.getLastColumn();
  const trailerURL = String(wsSpecs.getRange(rowNum, lastColSpecs - 1).getValue()).trim();

  // 2. Ανάγνωση βασικών μεταβλητών (χρησιμοποιώντας τις GLOBAL σταθερές σου)
  const sku = String(rowData[COL_SKU - 1]).trim();
  const prodTitle = String(rowData[COL_TITLE - 1]).trim();
  const prodIntro = String(rowData[COL_INTRO - 1]).trim();
  const numParagraphs = parseInt(rowData[COL_PAR_COUNT - 1]) || 0;
  const bannerIndicator = String(rowData[COL_BANNER_FLAG - 1]).trim().toUpperCase();
  const catLinkHtml = String(rowData[COL_CATLINK - 1] || ''); // Το link από το Step 3
  const techsVal = String(rowData[COL_TECHSPECS_HTML - 1] || '').trim(); // Το HTML από το Step 4

  // Αν δεν υπάρχει τίτλος, σταμάτα
  if (!prodTitle) return;

  // 3. VALIDATION ΛΟΓΙΚΗ (Η δική σου)
  if (numParagraphs > 0) {
    if (!prodIntro) return; // Αν λείπει η εισαγωγή, ακύρωση

    const requiredContentCols = [COL_SEC1_BODY, COL_SEC2_BODY, COL_SEC3_BODY, COL_SEC4_BODY, COL_SEC5_BODY, COL_SEC6_BODY];
    for (let i = 0; i < numParagraphs && i < 6; i++) {
      if (!String(rowData[requiredContentCols[i] - 1]).trim()) return; 
    }
  }

  // 4. ΧΤΙΣΙΜΟ HTML
  let finalHTML = '<div class="rich-multemedia">\n';

  // --- Banner Section ---
  if (bannerIndicator === 'YES' && sku) {
    finalHTML += 
      '<section class="one-column">\n' +
      '  <figure class="column img-shadow embed-responsive aspect-ration-nbyn">\n' +
      '    <picture>\n' +
      `      <source media="(min-width: 820px)" srcset="https://webstorage.public.gr/Product-Images/${sku}/bannerd.jpg">\n` +
      `      <img class="fade-in embed-responsive-item" src="https://webstorage.public.gr/Product-Images/${sku}/bannerm.jpg" alt="" loading="lazy">\n` +
      '    </picture>\n' +
      '  </figure>\n' +
      '</section>\n';
  }

  // --- Main Product & Intro ---
  if (sku && prodTitle) {
    finalHTML += 
      '<section class="two-column">\n' +
      '  <div class="column d-none d-sm-block">\n' +
      '    <figure class="embed-responsive embed-responsive-16by9">\n' +
      `      <img class="embed-responsive-item" src="https://webstorage.public.gr/Product-Images/${sku}/main.jpg" alt="" loading="lazy">\n` +
      '    </figure>\n' +
      '  </div>\n' +
      '  <div class="column">\n' +
      `    <h3><strong>${prodTitle}</strong></h3>\n` +
      `    <div class="body-text"><p>${prodIntro}${catLinkHtml}</p></div>\n` +
      '  </div>\n' +
      '</section>\n';
  }

  // --- Tech Specs Block (από Step 4) ---
  if (techsVal) finalHTML += techsVal + '\n';

  // --- Trailer Section ---
  if (trailerURL && trailerURL !== '-') {
    finalHTML += 
      '<section class="one-column">\n' +
      '  <div class="column embed-responsive embed-responsive-16by9">\n' +
      `    <iframe class="fade-in" title="${prodTitle}" src="${trailerURL}" allow="accelerometer; autoplay; encrypted-media; gyroscope; picture-in-picture" allowfullscreen></iframe>\n` +
      '  </div>\n' +
      '</section>\n';
  }

  // --- Δυναμικά Sections (BC1 - BC6) ---
  const headerCols = [COL_SEC1_HDR, COL_SEC2_HDR, COL_SEC3_HDR, COL_SEC4_HDR, COL_SEC5_HDR, COL_SEC6_HDR];
  const contentCols = [COL_SEC1_BODY, COL_SEC2_BODY, COL_SEC3_BODY, COL_SEC4_BODY, COL_SEC5_BODY, COL_SEC6_BODY];

  for (let idx = 0; idx < 6; idx++) {
    const headerVal = String(rowData[headerCols[idx] - 1]).trim();
    const contentVal = String(rowData[contentCols[idx] - 1]).trim();
    
    if (headerVal && contentVal) {
      const sectionClass = (idx % 2 === 0) ? 'two-column reverse' : 'two-column';
      const imageNum = idx + 1;
      finalHTML += 
        `<section class="${sectionClass}">\n` +
        '  <div class="column">\n' +
        '    <figure class="embed-responsive embed-responsive-16by9">\n' +
        `      <img class="embed-responsive-item" src="https://webstorage.public.gr/Product-Images/${sku}/besco${imageNum}.jpg" alt="" loading="lazy">\n` +
        '    </figure>\n' +
        '  </div>\n' +
        '  <div class="column">\n' +
        `    <h3><strong>${headerVal}</strong></h3>\n` +
        `    <div class="body-text"><p>${contentVal}</p></div>\n` +
        '  </div>\n' +
        '</section>\n';
    }
  }

  finalHTML += '</div>';

  // 5. ΕΓΓΡΑΦΗ ΣΤΟ COLUMN AA
  wsBescos.getRange(rowNum, COL_FINAL_HTML).setValue(finalHTML);
}

// ============================================
// STEP 6: VALIDATE & CLEANUP (helpers)
// ============================================


/**
 * Επιστρέφει έγκυρη/«κουμπωμένη» τιμή παραγράφων χαρακτηριστικών.
 * - Μετατρέπει σε αριθμό
 * - Κλαμπάρει στο [0, MAX_FEATURE_PARAS]
 */
const MAX_FEATURE_PARAS = 12;

function requiredContentColFor(n) {
  const v = Number(n);
  if (Number.isNaN(v)) return 0;
  return Math.max(0, Math.min(MAX_FEATURE_PARAS, v));
}

// ============================================
// TECH
// ============================================
function buildStyle_Tech() {
  return `Γράψε SEO-friendly περιγραφή προϊόντος *Tech* στα ελληνικά.
- Ξεκίνα κατευθείαν με HTML (χωρίς προλόγους).
- Δομή:
  1. **Benefit**: άμεση αξία/τι κερδίζει ο χρήστης.
  2. **Solution**: τα χαρακτηριστικά που στηρίζουν την αξία.
- Ύφος:
  - Δεύτερο ενικό («εσύ», «σου»)
  - Σύντομες, σαφείς προτάσεις
  - Τεχνολογικά ακριβές, χωρίς υπερβολές
  - Σωστή γραμματική, χωρίς επινοημένες λέξεις
  - Επαγγελματικό ρεαλιστικό τόνο.
- Χρησιμοποίησε \`<strong>\` για keywords, τεχνολογίες & μοντέλο.
- Δώσε προτεραιότητα σε τεχνολογίες με ουσιαστικό πλεονέκτημα και καινοτομίες που διαφοροποιούν.
- Δώσε έμφαση σε απόδοση, αξιοπιστία, εργονομία, συνδεσιμότητα.
- Διαφοροποίησε με βάση brand, χρήση & τεχνολογίες.
- Χρησιμοποίησε αγγλικούς τεχνικούς όρους όπου χρειάζεται (π.χ. NC, Bluetooth codecs, Hi-Res Audio).
- **Positioning**:
  - Premium > καινοτομία, υψηλή απόδοση, εμπειρία χρήσης.
  - Value > πρακτικότητα, προσβασιμότητα, value proposition.
- Ανάδειξε τα σημαντικότερα χαρακτηριστικά με ακρίβεια & ελκυστικότητα.`;
}

function buildContent_Tech_Online(q, n) {
  const N = requiredContentColFor(n);
  return `Χρησιμοποίησε online αναζήτηση μόνο στο site του κατασκευαστή, αγνόησε τρίτες πηγές.
- Query: "${q}".
- Χρησιμοποίησε β΄ ενικό πρόσωπο.

Δομή κειμένου:
1. **Τίτλος**: marketing/lifestyle, 6-10 λέξεις, περιγράφει αξία/εμπειρία.
2. **Εισαγωγή (~550 χαρακτήρες)**:
   - Παρουσίαση προϊόντος με βασικά χαρακτηριστικά & οφέλη.
   - Πρακτική, τεχνολογικά ενημερωμένη, χωρίς υπερβολικό συναίσθημα ή δραματισμό.
   - Ανάδειξη αποδοτικότητας, αξιοπιστίας, εμπειρίας.
   - Εξήγηση τι το κάνει να ξεχωρίζει.
3. **Παράγραφοι χαρακτηριστικών** (μήκος ~550 χαρακτήρες η καθεμία):
   - Τίτλος ~8 λέξεων, θετικός & πρακτικός.
   - Δομή:
       - 1η πρόταση: Τι είναι.
       - Επόμενες: Πρακτικά οφέλη (ταχύτητα, αξιοπιστία, αυτονομία).
   - Συνολικός αριθμός παραγράφων: ${N}
   - Αν 0 > μόνο εισαγωγική παράγραφος.
   - Αν αφορά Laptop/Desktop/All-in-One > γράψε με τη σειρά για CPU, GPU, SSD, RAM, Οθόνη, Λογισμικό.`;
}

function buildContent_Tech_Offline(manualInfo, n, techSpecs) {
  const N = requiredContentColFor(n);
  return `- Βασίσου αποκλειστικά στο υλικό που σου δίνεται, μην εφευρίσκεις στοιχεία ή συμπληρώνεις κενά με πληροφορίες που γνώριζες γενικά.
- Μην προσθέτεις στοιχεία που δεν αναφέρονται ρητά.

Δομή κειμένου:
1) Τίτλος: marketing/lifestyle, 6-10 λέξεις, να αποδίδει την αξία/εμπειρία.
2) Εισαγωγή (~550 χαρακτήρες):
   - Παρουσίασε συνοπτικά το προϊόν με βασικά χαρακτηριστικά & οφέλη (απόδοση, συνδεσιμότητα, εμπειρία χρήσης).
   - Πρακτική, τεχνολογικά ενημερωμένη, χωρίς υπερβολικό συναίσθημα ή δραματισμό.
   - Ανάδειξε αποδοτικότητα, αξιοπιστία, εμπειρία.
   - Εξήγησε τι το κάνει να ξεχωρίζει στην κατηγορία.
3) Παράγραφοι χαρακτηριστικών (καθεμία ~550 χαρακτήρες):
   - Κάθε παράγραφος = 1 τεχνολογία/χαρακτηριστικό.
   - Τίτλος ~8 λέξεων, θετικός & πρακτικός.
   - Χρησιμοποίησε <strong> για keywords/τεχνολογίες/μοντέλο.
   - Δομή: 1η πρόταση = τι είναι, επόμενες = πρακτικά οφέλη (ταχύτητα, αξιοπιστία, συνδεσιμότητα, αυτονομία).
   - Συνολικός αριθμός παραγράφων: ${N} (αν 0 > μόνο εισαγωγή).

4) ###SOURCE_BLOCK###`;
}

// ============================================
// HOME
// ============================================
function buildStyle_Home() {
  return `Γράψε SEO-friendly περιγραφή προϊόντος *Home* στα ελληνικά.
- Ξεκίνα κατευθείαν με HTML (χωρίς προλόγους).
- Δομή:
  1. **Benefit**: άμεσο πρακτικό όφελος στην καθημερινότητα.
  2. **Solution**: σύντομη και κατανοητή παρουσίαση βασικών χαρακτηριστικών.
- Ύφος:
  - Δεύτερο ενικό («εσύ», «σου»)
  - Σύντομες σαφείς προτάσεις
  - Φιλικό, θετικό, πρακτικό, αλλά όχι υπερβολικό ή δραματικό.
  - Επαγγελματικό ρεαλιστικό τόνο.
  - Σωστή γραμματική, χωρίς επινοημένες λέξεις
- Χρησιμοποίησε \`<strong>\` για keywords, τεχνολογίες & μοντέλο.
- Δώσε έμφαση στη χαρά, τη φροντίδα και την εμπειρία που προσφέρει το προϊόν, όχι μόνο στα τεχνικά χαρακτηριστικά.
- Διαφοροποίησε με βάση brand και χρήση.
- Πρόταξε τεχνολογίες/χαρακτηριστικά με ουσιαστικό πλεονέκτημα και πραγματική διαφοροποίηση.
- Τόνισε πρακτικά οφέλη (π.χ. άνεση, εξοικονόμηση, βελτίωση εμπειρίας).
- Απόφυγε απλές/γενικές τεχνικές περιγραφές χωρίς πρακτική σύνδεση.
- **Positioning**:
  - Premium > ποιότητα, καινοτομία, εμπειρία.
  - Value > πρακτικότητα, ευκολία, συμφέρουσα επιλογή.
- Αναφορά σε ενεργειακή κλάση μόνο αν είναι USP.`;
}

function buildContent_Home_Online(q, n) {
  const N = requiredContentColFor(n);
  return `Χρησιμοποίησε online αναζήτηση μόνο στο site του κατασκευαστή, αγνόησε τρίτες πηγές.
- Query: "${q}".
Δομή κειμένου:
1) Τίτλος: marketing/lifestyle, 6-10 λέξεις, να αποδίδει την αξία/εμπειρία.
2) Εισαγωγή (~550 χαρακτήρες):
   - Παρουσίασε συνοπτικά το προϊόν με βασικά χαρακτηριστικά & πρακτικά οφέλη.
   - Ύφος πρακτικό, σαφές, θετικό (χωρίς υπερβολές ).
   - Τόνισε βελτιώσεις στην καθημερινότητα (άνεση, ευκολία, απόδοση).
   - Εξήγησε τι το διαφοροποιεί από την κατηγορία του.
3) Παράγραφοι χαρακτηριστικών (καθεμία ~550 χαρακτήρες):
   - Κάθε παράγραφος καλύπτει 1 τεχνολογία/χαρακτηριστικό.
   - Τίτλος ~8 λέξεων, θετικός & πρακτικός.
   - Προτείνεται χρήση <strong> για το όνομα της τεχνολογίας/χαρακτηριστικού.
   - Δομή: 1η πρόταση = τι είναι, επόμενες = πρακτικά οφέλη για την καθημερινότητα.
   - Συνολικός αριθμός παραγράφων: ${N}.
   - Αν 0 > δημιούργησε μόνο την εισαγωγική παράγραφο.`;
}

function buildContent_Home_Offline(manualInfo, n, techSpecs) {
  const N = requiredContentColFor(n);
  return `- Βασίσου αποκλειστικά στο υλικό που σου δίνεται, μην εφευρίσκεις στοιχεία ή συμπληρώνεις κενά με πληροφορίες που γνώριζες γενικά.
- Μην προσθέτεις στοιχεία που δεν αναφέρονται ρητά.

Δομή κειμένου:
1) Τίτλος: marketing/lifestyle, 6-10 λέξεις, να αποδίδει την αξία/εμπειρία.
2) Εισαγωγή (~550 χαρακτήρες):
   - Παρουσίασε συνοπτικά το προϊόν με βασικά χαρακτηριστικά & πρακτικά οφέλη.
   - Ύφος πρακτικό, σαφές, θετικό (χωρίς υπερβολές).
   - Τόνισε βελτιώσεις στην καθημερινότητα (άνεση, ευκολία, απόδοση).
   - Εξήγησε τι το διαφοροποιεί από την κατηγορία του.
3) Παράγραφοι χαρακτηριστικών (καθεμία ~550 χαρακτήρες):
   - Κάθε παράγραφος = 1 τεχνολογία/χαρακτηριστικό.
   - Τίτλος ~8 λέξεων, θετικός & πρακτικός.
   - Χρησιμοποίησε <strong> για keywords/τεχνολογίες/μοντέλο.
   - Δομή: 1η πρόταση = τι είναι, επόμενες = πρακτικά οφέλη.
   - Συνολικός αριθμός παραγράφων: ${N} (αν 0 > μόνο εισαγωγή).

4) ###SOURCE_BLOCK###`;
}

// ============================================
// ENTERTAINMENT
// ============================================
function buildStyle_Enter() {
  return `Γράψε SEO-friendly περιγραφή προϊόντος *Entertainment* στα ελληνικά.
- Ξεκίνα κατευθείαν με HTML (χωρίς προλόγους).
- Δομή:
  1. **Benefit**: άμεση εμπειρία & απόλαυση.
  2. **Solution**: χαρακτηριστικά που την υποστηρίζουν.
- Ύφος:
  - Δεύτερο ενικό («εσύ», «σου»)
  - Σύντομες, σαφείς προτάσεις
  - Ενθουσιώδες, αισθησιακό, αλλά όχι υπερβολικό
  - Σωστή γραμματική, χωρίς επινοημένες λέξεις
- Χρησιμοποίησε \`<strong>\` για keywords, τεχνολογίες & μοντέλο.
- Δώσε έμφαση στην εμπειρία (εικόνα, ήχος, gaming, ψυχαγωγία).
- Διατήρησε τεχνολογική ακρίβεια (π.χ. HDR formats, refresh rates, latency, audio codecs).
- **Positioning**:
  - Premium > κινηματογραφική εμπειρία, επιδόσεις image/audio, immersive gaming.
  - Value > εύκολη απόλαυση, plug-and-play, smart λειτουργίες με καλή τιμή.`;
}

function buildContent_Enter_Online(q, n) {
  const N = requiredContentColFor(n);
  return `Χρησιμοποίησε online αναζήτηση μόνο στο site του κατασκευαστή, αγνόησε τρίτες πηγές.
- Query: "${q}".
Δομή κειμένου:
1) Τίτλος: marketing/lifestyle, 6-10 λέξεις, να αποδίδει την αξία/εμπειρία.
2) Εισαγωγή (~550 χαρακτήρες):
   - Ξεκίνα με την υπόσχεση της εμπειρίας (έκφραση, δημιουργικότητα, ανακάλυψη, κοινή χαρά).
   - Ανάδειξε πώς συμβάλλει σε στιγμές δημιουργίας, επικοινωνίας, απόλαυσης.
   - Εξήγησε τι το διαφοροποιεί από την κατηγορία.
   - Προαιρετικά: με φειδώ πρόσθεσε βασικά χαρακτηριστικά που ενισχύουν την εμπειρία.
3) Παράγραφοι χαρακτηριστικών (καθεμία ~550 χαρακτήρες):
   - Κάθε παράγραφος = 1 δυνατότητα/χαρακτηριστικό που στηρίζει την εμπειρία.
   - Τίτλος ~8 λέξεων, θετικός & πρακτικός.
   - Προτείνεται χρήση <strong> για το όνομα τεχνολογίας/χαρακτηριστικού.
   - Δομή: 1η πρόταση = τι είναι, επόμενες = πώς ενισχύει την εμπειρία.
   - Συνολικός αριθμός παραγράφων: ${N}.
   - Αν 0 > δημιούργησε μόνο την εισαγωγική παράγραφο.`;
}

function buildContent_Enter_Offline(manualInfo, n, techSpecs) {
  const N = requiredContentColFor(n);
  return `- Βασίσου αποκλειστικά στο υλικό που σου δίνεται, μην εφευρίσκεις στοιχεία ή συμπληρώνεις κενά με πληροφορίες που γνώριζες γενικά.
- Μην προσθέτεις στοιχεία που δεν αναφέρονται ρητά.

Δομή κειμένου:
1) Τίτλος: marketing/lifestyle, 6-10 λέξεις, να αποδίδει την αξία/εμπειρία.
2) Εισαγωγή (~550 χαρακτήρες):
   - Ξεκίνα με την υπόσχεση της εμπειρίας (έκφραση, δημιουργικότητα, ανακάλυψη, κοινή χαρά).
   - Ανάδειξε πώς συμβάλλει σε στιγμές δημιουργίας, επικοινωνίας, απόλαυσης.
   - Εξήγησε τι το διαφοροποιεί από την κατηγορία.
   - Προαιρετικά: με φειδώ πρόσθεσε βασικά χαρακτηριστικά που ενισχύουν την εμπειρία.
3) Παράγραφοι χαρακτηριστικών (καθεμία ~550 χαρακτήρες):
   - Κάθε παράγραφος = 1 δυνατότητα/χαρακτηριστικό που στηρίζει την εμπειρία.
   - Τίτλος ~8 λέξεων, θετικός & πρακτικός.
   - Προτείνεται χρήση <strong> για το όνομα τεχνολογίας/χαρακτηριστικού.
   - Δομή: 1η πρόταση = τι είναι, επόμενες = πώς ενισχύει την εμπειρία.
   - Συνολικός αριθμός παραγράφων: ${N} (αν 0 > μόνο εισαγωγή).

4) ###SOURCE_BLOCK###`;
}

/**
 * Runs the full pipeline row-by-row for each active row.
 * Uses the existing step functions but processes one row at a time.
 */
function createDescription() {
  // 1. Καθαρισμός παλιών triggers για να ξεκινήσουμε καθαρά
  deleteBescosContinuationTriggers();
  // 2. Ξεκίνα από τη σειρά 2
  processBescosInBatches(2);
}

// Αυτή η συνάρτηση θα καλείται από το trigger
function continueBescosDescription() {
  const nextRow = parseInt(PropertiesService.getScriptProperties().getProperty('BESCOS_NEXT_ROW') || '2');
  processBescosInBatches(nextRow);
}

function processBescosInBatches(startRow) {
  const batchStartTime = new Date().getTime();
  const MAX_RUNTIME = 5.5 * 60 * 1000; 
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const ws = ss.getSheetByName('Bescos');
  const wsSpecs = ss.getSheetByName('Specs');
  const wsTech = ss.getSheetByName('TechSpecs');
  const lastRow = ws.getLastRow();

  // --- ΠΡΟΕΤΟΙΜΑΣΙΑ: Φόρτωση δεδομένων ΜΙΑ φορά πριν το loop ---
  const catLinksDict = buildCatLinksDict(); 
  const techRowMap = buildTechSpecsRowMap(); 
  const techData = wsTech.getDataRange().getValues(); 
  const specsData = wsSpecs.getDataRange().getValues(); 
  const specsHeaders = specsData[0].map(h => cleanLower(h)); 

  for (let r = startRow; r <= lastRow; r++) {
    if (new Date().getTime() - batchStartTime > MAX_RUNTIME) {
      Logger.log(`Approaching time limit at row ${r}, creating continuation trigger`);
      createBescosContinuationTrigger(r);
      ss.toast(`Batch completed. Continuing automatically in 1 minute...`, 'Progress', 5);
      return;
    }

    const sku = ws.getRange(r, COL_SKU).getValue();
    if (!sku) continue;

    const currentStatus = ws.getRange(r, COL_FINAL_HTML).getValue();
    if (currentStatus != "") continue; 

    ss.toast(`Processing batch starting from row ${startRow}...`, 'Processing', 5);

    try {

      ss.toast(`Processing product ${r-1} of ${lastRow-1}...`, 'Progress', 3);

      // 1. Step 3: Κατηγοριοποίηση (Περνάμε το dict)
      step3_OutputCatLinks(r, catLinksDict); 
      
      // 2. Step 1: Gemini (Περνάμε τα headers/specs για να μη τα ξαναδιαβάζει)
      step1_GenHTMLGemini(r, specsHeaders, specsData);
      
      // 3. Step 2: Parsing
      step2_ParseSections(r);
      
      // 4. Step 4: Tech Specs (Περνάμε όλα τα arrays)
      step4_ProcessSpecsRow(r, techRowMap, techData, specsHeaders, specsData);
      
      // 5. Step 5: Τελικό Merge
      step5_GenerateProductHTML(r);
      
      SpreadsheetApp.flush(); 
    } catch (e) {
      Logger.log("Error in row " + r + ": " + e.message);
    }
  }
  
  deleteBescosContinuationTriggers();
  ss.toast('Process completed.', 'Success', 5);
}

/**
 * Clears data from Bescos sheet (rows 2-101) 
 * and Specs sheet, preserving existing formatting.
 */
function clearBescosSheetData() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const wsBescos = ss.getSheetByName('Bescos');
  const wsSpecs = ss.getSheetByName('Specs');
  
  if (!wsBescos || !wsSpecs) {
    SpreadsheetApp.getUi().alert('Error: Bescos or Specs sheet not found');
    return;
  }
  
  // --- Clear Bescos sheet: rows 2-101, columns A-AH (1-34) ---
  const bescosStartRow = 2;
  const bescosEndRow = 101;
  const bescosStartCol = 1;  // Column A
  const bescosEndCol = 34;   // Column AH
  
  const bescosNumRows = bescosEndRow - bescosStartRow + 1;
  const bescosNumCols = bescosEndCol - bescosStartCol + 1;
  
  const bescosRange = wsBescos.getRange(bescosStartRow, bescosStartCol, bescosNumRows, bescosNumCols);
  
  // Only clear content (keeps existing colors/fonts)
  bescosRange.clearContent();
  
  
  // --- Clear Specs sheet ---
  const specsLastRow = wsSpecs.getLastRow();
  const specsLastCol = wsSpecs.getLastColumn();
  
  // Check if there is data to clear
  if (specsLastRow > 0 && specsLastCol > 0) {
    // NOTE: The original code cleared from Row 1. 
    // If you want to KEEP headers, change the '1' below to '2'.
    const specsRange = wsSpecs.getRange(1, 1, specsLastRow, specsLastCol);
    specsRange.clearContent();
  }
  
  SpreadsheetApp.flush();
  
  // Assuming showToast exists in your project, otherwise use ss.toast()
  try {
    showToast('Data cleared successfully (formatting preserved)', 'Done', 3);
  } catch (e) {
    ss.toast('Data cleared successfully (formatting preserved)');
  }
  
  Logger.log('Cleared Bescos and Specs content only');
}

function createBescosContinuationTrigger(nextRow) {
  deleteBescosContinuationTriggers(); // Καθαρισμός παλιών
  ScriptApp.newTrigger('continueBescosDescription')
    .timeBased()
    .after(60 * 1000) // Ξεκίνα πάλι σε 1 λεπτό
    .create();
  PropertiesService.getScriptProperties().setProperty('BESCOS_NEXT_ROW', nextRow.toString());
  Logger.log("Ορίστηκε trigger για τη σειρά: " + nextRow);
}

function deleteBescosContinuationTriggers() {
  const triggers = ScriptApp.getProjectTriggers();
  for (let i = 0; i < triggers.length; i++) {
    if (triggers[i].getHandlerFunction() === 'continueBescosDescription') {
      ScriptApp.deleteTrigger(triggers[i]);
    }
  }
}
