{
  description = "A little python tool to automatically fetch my current kindle notes.";

  inputs = {
    flake-utils.url = "github:numtide/flake-utils";
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable-small";
    poetry2nix = {
      url = "github:nix-community/poetry2nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs = inputs @ { self, nixpkgs, flake-utils, ... }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        poetry2nix = inputs.poetry2nix.lib.mkPoetry2Nix { inherit pkgs; };
        kindleFetch = poetry2nix.mkPoetryApplication {
            projectDir = self;
            preferWheels = true;
        };

      in
      {
        packages = {
          kindleFetch = kindleFetch;
          default = self.packages.${system}.kindleFetch;
        };

        apps.default = {
          type = "app";
          program = "${kindleFetch}/bin/kindle_fetch";
        };

        # Shell for app dependencies.
        #
        #     nix develop
        #
        # Use this shell for developing your app.
        devShells.default = pkgs.mkShell {
          inputsFrom = [ self.packages.${system}.kindleFetch ];
          package = with pkgs; [
            ruff
            pyright
            python3Packages.jupyter
          ];

          shellHook = ''
          export PYTHONPATH=$(pwd)/src:$PYTHONPATH
          '';
        };

        # Shell for poetry.
        #
        #     nix develop .#poetry
        #
        # Use this shell for changes to pyproject.toml and poetry.lock.
        devShells.poetry = pkgs.mkShell {
          packages = [ pkgs.poetry ];
        };
      });
}
