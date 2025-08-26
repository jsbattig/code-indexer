using System;
using System.Threading.Tasks;

namespace TestNamespace
{
    public class TestClass
    {
        private string _name;
        
        public TestClass(string name)
        {
            _name = name;
        }
        
        public async Task<T> GetAsync<T>(int id) where T : class
        {
            return await SomeAsyncOperation<T>(id);
        }
        
        public string Name { get; set; }
        
        public string FullName => $"{Name} Full";
        
        public event EventHandler<string> NameChanged;
        
        public static implicit operator string(TestClass test) => test.Name;
    }
}