const About = () => {
  return (
    <div className="max-w-3xl mx-auto px-6 sm:px-8 lg:px-10 py-12">
      {/* Hero Section */}
      <div className="text-center mb-12">
        <h1 className="text-4xl font-semibold text-afl-warm-900 mb-4">
          Footy-NAC
        </h1>
        <p className="text-xl text-afl-warm-500">
          Not Another Commentator
        </p>
      </div>

      {/* About Section */}
      <section className="card-apple p-8 mb-8">
        <h2 className="text-2xl font-semibold text-afl-warm-900 mb-4">
          Welcome to Footy-NAC
        </h2>
        <div className="text-afl-warm-700 space-y-4">
          <p>
            This app allows users to answer their weird couch questions. Like
            what game did a player get the most handballs in one game? Or who
            was it that kicked 1000 goals before Buddy?
          </p>
          <p>
            I also threw together a live stats view and AI summary for those
            who want a one-stop shop to get a view of games without needing to
            visit many different websites.
          </p>
        </div>
      </section>

      {/* About Me Section */}
      <section className="card-apple p-8 mb-8">
        <h2 className="text-2xl font-semibold text-afl-warm-900 mb-4">
          About Me
        </h2>
        <div className="text-afl-warm-700 space-y-4">
          <p>
            I am a Data Scientist who loves the AFL and wants an easier way to
            pull together fun stats.
          </p>
        </div>
      </section>

      {/* Connect Section */}
      <section className="card-apple p-8">
        <h2 className="text-2xl font-semibold text-afl-warm-900 mb-6">
          Connect & Support
        </h2>

        <div className="space-y-4">
          {/* Instagram */}
          <a
            href="https://instagram.com/footy.nac"
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-4 p-4 rounded-apple bg-gradient-to-r from-purple-500 to-pink-500
                       text-white hover:shadow-apple-md transition-all duration-200 hover:scale-[1.02]"
          >
            <svg className="w-8 h-8" fill="currentColor" viewBox="0 0 24 24">
              <path d="M12 2.163c3.204 0 3.584.012 4.85.07 3.252.148 4.771 1.691 4.919 4.919.058 1.265.069 1.645.069 4.849 0 3.205-.012 3.584-.069 4.849-.149 3.225-1.664 4.771-4.919 4.919-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-4.849-.07-3.26-.149-4.771-1.699-4.919-4.92-.058-1.265-.07-1.644-.07-4.849 0-3.204.013-3.583.07-4.849.149-3.227 1.664-4.771 4.919-4.919 1.266-.057 1.645-.069 4.849-.069zm0-2.163c-3.259 0-3.667.014-4.947.072-4.358.2-6.78 2.618-6.98 6.98-.059 1.281-.073 1.689-.073 4.948 0 3.259.014 3.668.072 4.948.2 4.358 2.618 6.78 6.98 6.98 1.281.058 1.689.072 4.948.072 3.259 0 3.668-.014 4.948-.072 4.354-.2 6.782-2.618 6.979-6.98.059-1.28.073-1.689.073-4.948 0-3.259-.014-3.667-.072-4.947-.196-4.354-2.617-6.78-6.979-6.98-1.281-.059-1.69-.073-4.949-.073zm0 5.838c-3.403 0-6.162 2.759-6.162 6.162s2.759 6.163 6.162 6.163 6.162-2.759 6.162-6.163c0-3.403-2.759-6.162-6.162-6.162zm0 10.162c-2.209 0-4-1.79-4-4 0-2.209 1.791-4 4-4s4 1.791 4 4c0 2.21-1.791 4-4 4zm6.406-11.845c-.796 0-1.441.645-1.441 1.44s.645 1.44 1.441 1.44c.795 0 1.439-.645 1.439-1.44s-.644-1.44-1.439-1.44z" />
            </svg>
            <div>
              <p className="font-semibold">Follow on Instagram</p>
              <p className="text-sm opacity-80">@footy.nac</p>
            </div>
          </a>

          {/* Buy Me a Coffee */}
          <a
            href="https://buymeacoffee.com/footy.nac"
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-4 p-4 rounded-apple bg-[#FFDD00] text-black
                       hover:shadow-apple-md transition-all duration-200 hover:scale-[1.02]"
          >
            <svg className="w-8 h-8" viewBox="0 0 24 24" fill="currentColor">
              <path d="M20.216 6.415l-.132-.666c-.119-.598-.388-1.163-1.001-1.379-.197-.069-.42-.098-.57-.241-.152-.143-.196-.366-.231-.572-.065-.378-.125-.756-.192-1.133-.057-.325-.102-.69-.25-.987-.195-.4-.597-.634-.996-.788a5.723 5.723 0 00-.626-.194c-1-.263-2.05-.36-3.077-.416a25.834 25.834 0 00-3.7.062c-.915.083-1.88.184-2.75.5-.318.116-.646.256-.888.501-.297.302-.393.77-.177 1.146.154.267.415.456.692.58.36.162.737.284 1.123.366 1.075.238 2.189.331 3.287.37 1.218.05 2.437.01 3.65-.118.299-.033.598-.073.896-.119.352-.054.578-.513.474-.834-.124-.383-.457-.531-.834-.473-.466.074-.96.108-1.382.146-1.177.08-2.358.082-3.536.006a22.228 22.228 0 01-1.157-.107c-.086-.01-.18-.025-.258-.036-.243-.036-.484-.08-.724-.13-.111-.027-.111-.185 0-.212h.005c.277-.06.557-.108.838-.147h.002c.131-.009.263-.032.394-.048a25.076 25.076 0 013.426-.12c.674.019 1.347.067 2.017.144l.228.031c.267.04.533.088.798.145.392.085.895.113 1.07.542.055.137.08.288.111.431l.319 1.484a.237.237 0 01-.199.284h-.003c-.037.006-.075.01-.112.015a36.704 36.704 0 01-4.743.295 37.059 37.059 0 01-4.699-.304c-.14-.017-.293-.042-.417-.06-.326-.048-.649-.108-.973-.161-.393-.065-.768-.032-1.123.161-.29.16-.527.404-.675.701-.154.316-.199.66-.267 1-.069.34-.176.707-.135 1.056.087.753.613 1.365 1.37 1.502a39.69 39.69 0 0011.343.376.483.483 0 01.535.53l-.071.697-1.018 9.907c-.041.41-.047.832-.125 1.237-.122.637-.553 1.028-1.182 1.171-.577.131-1.165.2-1.756.205-.656.004-1.31-.025-1.966-.022-.699.004-1.556-.06-2.095-.58-.475-.458-.54-1.174-.605-1.793l-.731-7.013-.322-3.094c-.037-.351-.286-.695-.678-.678-.336.015-.718.3-.678.679l.228 2.185.949 9.112c.147 1.344 1.174 2.068 2.446 2.272.742.12 1.503.144 2.257.156.966.016 1.942.053 2.892-.122 1.408-.258 2.465-1.198 2.616-2.657.34-3.332.683-6.663 1.024-9.995l.215-2.087a.484.484 0 01.39-.426c.402-.078.787-.212 1.074-.518.455-.488.546-1.124.385-1.766zm-1.478.772c-.145.137-.363.201-.578.233-2.416.359-4.866.54-7.308.46-1.748-.06-3.477-.254-5.207-.498-.17-.024-.353-.055-.47-.18-.22-.236-.111-.71-.054-.995.052-.26.152-.609.463-.646.484-.057 1.046.148 1.526.22.577.088 1.156.159 1.737.212 2.48.226 5.002.19 7.472-.14.45-.06.899-.13 1.345-.21.399-.072.84-.206 1.08.206.166.281.188.657.162.974a.544.544 0 01-.169.364z" />
            </svg>
            <div>
              <p className="font-semibold">Buy Me a Coffee</p>
              <p className="text-sm opacity-70">Support the project</p>
            </div>
          </a>
        </div>
      </section>

      {/* Footer */}
      <footer className="text-center mt-12 text-sm text-afl-warm-500">
        <p>&copy; {new Date().getFullYear()} Footy-NAC. All rights reserved.</p>
      </footer>
    </div>
  );
};

export default About;
