// Type-checks the hand-written declaration files (`.d.ts`) of a project. `vue-tsc --build` needs
// `skipLibCheck`, because some packages' declarations have errors nobody here can fix, and it skips ours
// too: a broken import in one left its types as `any` and passed. Only the errors of our own files count.
import ts from 'typescript';

const host: ts.FormatDiagnosticsHost = {
  getCanonicalFileName: (fileName) => fileName,
  getCurrentDirectory: ts.sys.getCurrentDirectory,
  getNewLine: () => ts.sys.newLine,
};

function parse(project: string): ts.ParsedCommandLine {
  const parsed = ts.getParsedCommandLineOfConfigFile(
    project,
    { skipLibCheck: false },
    {
      ...ts.sys,
      onUnRecoverableConfigFileDiagnostic: (diagnostic) => {
        throw new Error(ts.formatDiagnostic(diagnostic, host));
      },
    },
  );
  if (!parsed) throw new Error(`${project} could not be parsed`);
  if (parsed.errors.length > 0) throw new Error(ts.formatDiagnostics(parsed.errors, host));
  return parsed;
}

/** The errors of the declaration files the project lists. */
function declarationErrors(project: string): ts.Diagnostic[] {
  const parsed = parse(project);
  const declarations = parsed.fileNames.filter((fileName) => fileName.endsWith('.d.ts'));
  const program = ts.createProgram({ rootNames: declarations, options: parsed.options });
  return declarations.flatMap((fileName) => {
    const file = program.getSourceFile(fileName);
    return [...program.getSyntacticDiagnostics(file), ...program.getSemanticDiagnostics(file)];
  });
}

const errors = declarationErrors(process.argv[2]);
if (errors.length > 0) {
  process.stderr.write(ts.formatDiagnostics(errors, host));
  process.exitCode = 1;
}
